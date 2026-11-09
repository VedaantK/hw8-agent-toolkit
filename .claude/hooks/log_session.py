#!/usr/bin/env python3
"""Claude Code hook: keeps HW8 evidence logs up to date automatically.

  UserPromptSubmit -> appends the prompt, verbatim, to prompt_log.md
  Stop / SessionEnd -> copies the raw session transcript (.jsonl) into
                       transcripts/ and renders a readable .md version that
                       shows every tool call (including MCP calls), so it can
                       be trimmed and pasted into DEMONSTRATION.md.

Never blocks Claude: any error is written to stderr and the hook exits 0.
"""
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPT_LOG = os.path.join(ROOT, "prompt_log.md")
TRANSCRIPTS = os.path.join(ROOT, "transcripts")


def log_prompt(data):
    prompt = data.get("prompt", "")
    sid = data.get("session_id", "?")[:8]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quoted = "\n".join("> " + line for line in prompt.splitlines()) or "> "
    with open(PROMPT_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n### {ts} · session `{sid}`\n\n{quoted}\n")


def short(value, limit=600):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + f" …[+{len(text) - limit} chars]"


def render(jsonl_path, md_path, sid):
    out = [f"# Transcript `{sid}`\n", f"Source: `{os.path.basename(jsonl_path)}`\n"]
    with open(jsonl_path, encoding="utf-8") as f:
        for raw in f:
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = entry.get("type")
            if kind not in ("user", "assistant"):
                continue
            msg = entry.get("message") or {}
            content = msg.get("content")
            ts = (entry.get("timestamp") or "")[:19].replace("T", " ")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for block in content or []:
                btype = block.get("type")
                if btype == "text" and block.get("text", "").strip():
                    who = "USER" if kind == "user" else "CLAUDE"
                    out.append(f"\n**{who}** ({ts}):\n\n{block['text'].strip()}\n")
                elif btype == "tool_use":
                    out.append(f"\n**TOOL CALL → `{block.get('name')}`** ({ts})\n\n"
                               f"```json\n{short(block.get('input'))}\n```\n")
                elif btype == "tool_result":
                    res = block.get("content")
                    if isinstance(res, list):
                        res = "\n".join(c.get("text", "") for c in res if isinstance(c, dict))
                    out.append(f"\n<details><summary>tool result</summary>\n\n```\n"
                               f"{short(res or '', 1500)}\n```\n</details>\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("".join(out))


def save_transcript(data):
    src = data.get("transcript_path")
    if not src or not os.path.exists(src):
        return
    sid = data.get("session_id", "unknown")
    os.makedirs(TRANSCRIPTS, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    base = os.path.join(TRANSCRIPTS, f"{day}_{sid[:8]}")
    shutil.copyfile(src, base + ".jsonl")
    render(src, base + ".md", sid[:8])


def main():
    try:
        data = json.load(sys.stdin)
        event = data.get("hook_event_name", "")
        if event == "UserPromptSubmit":
            log_prompt(data)
        elif event in ("Stop", "SessionEnd"):
            save_transcript(data)
    except Exception as exc:  # never break the session over logging
        print(f"log_session hook error: {exc}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
