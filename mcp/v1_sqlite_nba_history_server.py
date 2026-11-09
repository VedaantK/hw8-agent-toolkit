"""nba-history: an MCP server with one tool that reads real NBA box scores
from my nbaPred SQLite database (read-only).

Run standalone:   python mcp/nba_history_server.py      (waits on stdin; Ctrl+C to quit)
Config:           NBA_DB_PATH env var -> path to nba_predictor.db
                  (default: ~/Documents/GitHub/nbaPred/data/nba_predictor.db, machine-specific)

Logging goes to stderr only. Writing to stdout would corrupt the MCP stdio protocol.
"""
import difflib
import os
import sqlite3
import statistics
import sys
import unicodedata
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(os.environ.get(
    "NBA_DB_PATH",
    Path.home() / "Documents/GitHub/nbaPred/data/nba_predictor.db",
)).expanduser()

mcp = FastMCP("nba-history")


def log(msg: str) -> None:
    print(f"[nba-history] {msg}", file=sys.stderr, flush=True)


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}. Set NBA_DB_PATH.")
    # mode=ro: the tool can never write to the database.
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def fold(text: str) -> str:
    """Lowercase and strip accents so 'jokic' matches 'Nikola Jokić'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c)).lower().strip()


def resolve_player(conn: sqlite3.Connection, query: str):
    """Return (player_id, name) or an error string listing candidates."""
    players = conn.execute(
        "SELECT player_id, player_name FROM player_game_logs GROUP BY player_id"
    ).fetchall()
    q = fold(query)
    exact = [p for p in players if fold(p[1]) == q]
    if exact:
        return exact[0]
    # Every word typed must start a word of the name: "smith" must not match "Nesmith".
    words = q.replace(".", "").split()
    partial = [p for p in players
               if all(any(t.startswith(w) for t in fold(p[1]).replace(".", "").split())
                      for w in words)]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = ", ".join(sorted(p[1] for p in partial))
        return f"'{query}' matches several players: {names}. Ask again with the full name."
    close = difflib.get_close_matches(q, [fold(p[1]) for p in players], n=3, cutoff=0.6)
    hint = f" Closest names: {', '.join(close)}." if close else ""
    return (f"No player matching '{query}' in the database "
            f"(it tracks {len(players)} players, not the whole league).{hint}")


def fmt_avg(values) -> str:
    return f"{statistics.mean(values):.1f}" if values else "n/a"


@mcp.tool()
def player_history(player: str, last_n: int = 10, opponent: str = "",
                   season: str = "", line: float | None = None) -> str:
    """Look up an NBA player's real recent box scores from my local nbaPred database.

    Use this whenever a question needs actual NBA player numbers: recent scoring,
    points/rebounds/assists averages, minutes, form, home vs away splits, how a player
    has done against a specific team, or how often they went over a points line.
    Do not answer those from memory. Your training data is out of date and these
    are the real game logs.

    Args:
        player: Full or partial name, accents optional (e.g. "Jalen Brunson", "jokic").
        last_n: How many of the most recent games to include (1-82, default 10).
        opponent: Optional 3-letter team code (e.g. "BOS") to only count games vs that team.
        season: Optional season like "2025-26". Default is all seasons, newest first.
        line: Optional points line (e.g. 25.5). Reports how many games went over it.

    Returns plain text: the date range the database covers, a per-game table, and
    averages, median, range, and home/away splits. The database only covers the
    players and dates it has been backfilled with. The first line always says the
    latest game date available, so never describe these numbers as "this season" or
    "current" without checking that date.
    """
    last_n = max(1, min(int(last_n), 82))
    log(f"player_history(player={player!r}, last_n={last_n}, opponent={opponent!r}, "
        f"season={season!r}, line={line})")
    try:
        conn = connect()
    except Exception as exc:  # report, don't crash the server
        return f"ERROR: {exc}"

    with conn:
        newest, = conn.execute("SELECT MAX(game_date) FROM player_game_logs").fetchone()
        found = resolve_player(conn, player)
        if isinstance(found, str):
            return f"Database covers games through {newest}.\n{found}"
        pid, name = found

        sql = ("SELECT game_date, season, matchup, is_home, wl, minutes, points, rebounds, "
               "assists, fgm, fga, fg3m FROM player_game_logs WHERE player_id = ?")
        args: list = [pid]
        if season:
            sql += " AND season = ?"
            args.append(season)
        if opponent:
            sql += " AND UPPER(SUBSTR(TRIM(matchup), -3)) = ?"
            args.append(opponent.strip().upper())
        sql += " ORDER BY game_date DESC LIMIT ?"
        args.append(last_n)
        rows = conn.execute(sql, args).fetchall()

    scope = " ".join(filter(None, [f"vs {opponent.upper()}" if opponent else "",
                                   f"in {season}" if season else ""]))
    header = f"Database covers games through {newest}.\n{name}: last {len(rows)} games {scope}".rstrip()
    if not rows:
        return header + "\nNo games found for that filter."

    pts = [r[6] for r in rows if r[6] is not None]
    mins = [r[5] for r in rows if r[5] is not None]
    home = [r[6] for r in rows if r[3] == 1 and r[6] is not None]
    away = [r[6] for r in rows if r[3] == 0 and r[6] is not None]

    out = [header, "",
           "date        matchup        W/L  MIN   PTS  REB  AST  FG     3PM"]
    for d, _s, mu, _h, wl, mn, p, rb, a, fgm, fga, f3 in rows:
        out.append(f"{d}  {(mu or ''):<13}  {wl or '-':<3}  {mn or 0:>4.0f}  {p:>4}  {rb:>3}  "
                   f"{a:>3}  {fgm}/{fga:<4} {f3}")
    out += ["",
            f"PTS avg {fmt_avg(pts)} | median {statistics.median(pts):g} | "
            f"range {min(pts)}-{max(pts)} | MIN avg {fmt_avg(mins)}",
            f"Home avg {fmt_avg(home)} ({len(home)} g) | Away avg {fmt_avg(away)} ({len(away)} g)"]
    if line is not None:
        over = sum(p > line for p in pts)
        out.append(f"Over {line} pts: {over} of {len(pts)} games ({over / len(pts):.0%})")
    return "\n".join(out)


if __name__ == "__main__":
    log(f"starting; database = {DB_PATH}")
    mcp.run()  # stdio transport
