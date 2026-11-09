"""nba-history (v2): an MCP server with one tool that returns real NBA player game logs
from ESPN's free public API (no key needed), including the current season.

Run standalone:   python mcp/nba_history_server.py      (waits on stdin; Ctrl+C to quit)

ESPN URL patterns were adapted from Left-Coast-Tech/espn-mcp (MIT,
https://github.com/Left-Coast-Tech/espn-mcp). That project only exposes team-level data
(scoreboard, standings, schedules). The player search + game log lookup and the
prop-style analysis here are new.

v1 (v1_sqlite_nba_history_server.py) read my local nbaPred SQLite file instead. That data
stopped in April 2026 and only covered 134 players whose names start with A–D.

Logging goes to stderr only. Writing to stdout would corrupt the MCP stdio protocol.
"""
import json
import statistics
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

SEARCH_URL = "https://site.web.api.espn.com/apis/common/v3/search"
GAMELOG_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{id}/gamelog"
ET = ZoneInfo("America/New_York")
CACHE_SECONDS = 600  # be polite to ESPN: repeat questions within 10 min reuse the response

# ESPN abbreviations that differ from the NBA's official 3-letter codes.
ESPN_TO_NBA = {"NY": "NYK", "SA": "SAS", "GS": "GSW", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}

mcp = FastMCP("nba-history")
_cache: dict[str, tuple[float, dict]] = {}


def log(msg: str) -> None:
    print(f"[nba-history] {msg}", file=sys.stderr, flush=True)


def get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    hit = _cache.get(full)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    req = urllib.request.Request(full, headers={"User-Agent": "hw8-nba-history/2.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    _cache[full] = (time.time(), data)
    return data


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c)).lower().strip()


def nba_code(abbr: str) -> str:
    abbr = (abbr or "").upper()
    return ESPN_TO_NBA.get(abbr, abbr)


def season_label(end_year: int) -> str:
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def current_season_end_year(today: datetime) -> int:
    # NBA seasons start in October: Oct 2026 -> the 2026-27 season (ESPN calls it 2027).
    return today.year + 1 if today.month >= 10 else today.year


def find_player(name: str):
    """Return (espn_id, display_name) or an error string."""
    items = get_json(SEARCH_URL, {"query": name, "limit": 20, "type": "player"}).get("items", [])
    nba = [i for i in items if i.get("league") == "nba"]
    if not nba:
        return f"No NBA player found on ESPN matching '{name}'. Check the spelling or use the full name."
    q = fold(name)
    exact = [i for i in nba if fold(i["displayName"]) == q]
    if exact or len(nba) == 1:
        p = (exact or nba)[0]
        return p["id"], p["displayName"]
    names = ", ".join(i["displayName"] for i in nba[:8])
    return f"'{name}' matches several NBA players: {names}. Ask again with the full name."


def season_games(espn_id: str, end_year: int) -> list[dict]:
    """All regular-season and playoff games for one season, newest first. Preseason skipped."""
    data = get_json(GAMELOG_URL.format(id=espn_id), {"season": end_year})
    labels = data.get("labels", [])
    events = data.get("events", {})
    games = []
    for stype in data.get("seasonTypes", []):
        kind = stype.get("displayName", "")
        if "Preseason" in kind:
            continue
        for cat in stype.get("categories", []):
            for ev in cat.get("events", []):
                meta = events.get(ev.get("eventId"), {})
                stats = dict(zip(labels, ev.get("stats", [])))
                if not meta or not stats:
                    continue
                when = datetime.fromisoformat(meta["gameDate"].replace("Z", "+00:00")).astimezone(ET)
                games.append({
                    "date": when.date().isoformat(),
                    "season": season_label(end_year),
                    "playoffs": "Postseason" in kind,
                    "home": meta.get("atVs") == "vs",
                    "opp": nba_code(meta.get("opponent", {}).get("abbreviation", "")),
                    "team": nba_code(meta.get("team", {}).get("abbreviation", "")),
                    "result": meta.get("gameResult", "-"),
                    "min": stats.get("MIN", "0"), "pts": int(stats.get("PTS", 0) or 0),
                    "reb": stats.get("REB", "0"), "ast": stats.get("AST", "0"),
                    "fg": stats.get("FG", "-"), "3pt": stats.get("3PT", "-"),
                })
    return sorted(games, key=lambda g: g["date"], reverse=True)


def avg(values) -> str:
    return f"{statistics.mean(values):.1f}" if values else "n/a"


@mcp.tool()
def player_history(player: str, last_n: int = 10, opponent: str = "",
                   season: str = "", line: float | None = None) -> str:
    """Look up an NBA player's real game-by-game box scores from ESPN, current season included.

    Use this whenever a question needs actual NBA player numbers: recent scoring,
    points/rebounds/assists, minutes, form or slumps, home vs away splits, how a player
    has done against a specific team, or how often they went over a points line (props).
    Do not answer those from memory. Your training data is out of date and this is live data.

    Args:
        player: Player name, accents optional (e.g. "Jalen Brunson", "Nikola Jokic").
        last_n: How many most-recent games to include (1-82, default 10).
        opponent: Optional team code to only count games vs that team (e.g. "BOS", "NYK").
            Searches back up to 3 seasons.
        season: Optional season like "2025-26". Default: most recent games, going back
            into last season if this season has fewer than last_n games.
        line: Optional points line (e.g. 25.5). Reports how many games went over it.

    Returns plain text: data source and fetch time, a per-game table (playoff games
    marked PO), and points average/median/range plus home/away splits. Preseason is
    excluded. Always mention the date of the latest game when you report these numbers.
    """
    last_n = max(1, min(int(last_n), 82))
    opponent = nba_code(opponent.strip()) if opponent else ""
    log(f"player_history(player={player!r}, last_n={last_n}, opponent={opponent!r}, "
        f"season={season!r}, line={line})")
    now = datetime.now(ET)
    try:
        found = find_player(player)
        if isinstance(found, str):
            return found
        espn_id, name = found

        if season:
            try:
                years = [int(season.split("-")[0]) + 1]
            except ValueError:
                return f"Season '{season}' not understood. Use the form '2025-26'."
        else:
            cur = current_season_end_year(now)
            years = [cur, cur - 1, cur - 2] if opponent else [cur, cur - 1]

        games: list[dict] = []
        for y in years:
            games += [g for g in season_games(espn_id, y) if not opponent or g["opp"] == opponent]
            if len(games) >= last_n:
                break
        rows = games[:last_n]
    except Exception as exc:  # report the failure to the agent instead of crashing the server
        log(f"error: {exc!r}")
        return f"ERROR fetching ESPN data: {exc}. Do not fill in numbers from memory."

    scope = " ".join(filter(None, [f"vs {opponent}" if opponent else "",
                                   f"in {season}" if season else ""]))
    out = [f"Source: ESPN public API, fetched {now:%Y-%m-%d %H:%M} ET",
           f"{name}: last {len(rows)} games {scope}".rstrip()]
    if not rows:
        return "\n".join(out + ["No games found for that filter."])

    out += ["", "date        season   opp        W/L  MIN  PTS  REB  AST  FG      3PT"]
    for g in rows:
        opp = ("vs " if g["home"] else "@ ") + g["opp"] + (" PO" if g["playoffs"] else "")
        out.append(f"{g['date']}  {g['season']}  {opp:<10}{g['result']:<3}  {g['min']:>3}  "
                   f"{g['pts']:>3}  {g['reb']:>3}  {g['ast']:>3}  {g['fg']:<7} {g['3pt']}")
    pts = [g["pts"] for g in rows]
    home = [g["pts"] for g in rows if g["home"]]
    away = [g["pts"] for g in rows if not g["home"]]
    out += ["",
            f"PTS avg {avg(pts)} | median {statistics.median(pts):g} | range {min(pts)}-{max(pts)}",
            f"Home avg {avg(home)} ({len(home)} g) | Away avg {avg(away)} ({len(away)} g)",
            f"Latest game in this result: {rows[0]['date']}"]
    if line is not None:
        over = sum(p > line for p in pts)
        out.append(f"Over {line} pts: {over} of {len(pts)} games ({over / len(pts):.0%})")
    return "\n".join(out)


if __name__ == "__main__":
    log("starting (ESPN public API)")
    mcp.run()  # stdio transport
