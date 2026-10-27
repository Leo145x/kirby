#!/usr/bin/env python3
"""Print what happened in the newest Claude Code or Codex session run in a project directory, one JSON
object per line, for checking a test case's outputs without reading the screen.

    transcript.py claude /path/to/project      # newest Claude Code session there
    transcript.py codex /path/to/project       # newest Codex session there
    transcript.py claude /path/to/project --file <session.jsonl>
    transcript.py claude /path/to/project --tool install --last 1   # the newest install call only

Each line is one of:
    {"t": "user", "text": …}                    what the user sent
    {"t": "say", "text": …}                     what the model wrote
    {"t": "tool", "name": …, "input": …, "result": …}

Claude Code tool names are as the model saw them (mcp__kirby__install, Bash, …); Codex MCP calls are
named mcp__<server>__<tool> to match. Results are text. Sessions are looked up under
$CLAUDE_CONFIG_DIR and $CODEX_HOME when those are set, as the agent CLIs store them.
"""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def claude_file(project):
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    folder = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path(project).resolve()))
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no Claude Code session for {project} (looked in {folder})")
    return files[-1]


def codex_file(project):
    want = str(Path(project).resolve())
    files = sorted((Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions").glob("*/*/*/rollout-*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        with f.open() as fh:
            first = json.loads(fh.readline() or "{}")
        meta = first.get("payload") or {}
        # Codex runs subagents (such as the approval reviewer) in the same cwd; skip them.
        if meta.get("cwd") == want and not meta.get("parent_thread_id"):
            return f
    sys.exit(f"no Codex session for {project}")


def claude_events(path):
    calls, out = {}, []
    for line in path.open():
        r = json.loads(line)
        # Only user and assistant records; others (api-request-blob, …) repeat what they hold.
        if r.get("type") not in ("user", "assistant"):
            continue
        m = r.get("message") or {}
        c = m.get("content")
        if m.get("role") == "user" and isinstance(c, str):
            out.append({"t": "user", "text": c})
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "text" and m.get("role") == "assistant":
                out.append({"t": "say", "text": b["text"]})
            elif b.get("type") == "tool_use":
                calls[b["id"]] = {"t": "tool", "name": b.get("name"), "input": b.get("input"), "result": None}
                out.append(calls[b["id"]])
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                calls[b["tool_use_id"]]["result"] = text_of(b.get("content"))
    return out


def codex_events(path):
    out = []
    for line in path.open():
        p = json.loads(line).get("payload") or {}
        if p.get("type") != "item_completed":
            continue
        it = p.get("item") or {}
        kind = it.get("type")
        if kind == "UserMessage":
            out.append({"t": "user", "text": text_of(it.get("content"))})
        elif kind == "AgentMessage":
            out.append({"t": "say", "text": text_of([{"text": c.get("text", "")} for c in it.get("content") or []])})
        elif kind == "McpToolCall":
            # Codex stores the MCP result as a dict, or as the repr of one.
            result = it.get("result")
            if isinstance(result, str):
                try:
                    result = ast.literal_eval(result)
                except (ValueError, SyntaxError):
                    pass
            if isinstance(result, dict):
                result = text_of(result.get("content"))
            out.append({"t": "tool", "name": f"mcp__{it.get('server')}__{it.get('tool')}",
                        "input": it.get("arguments"), "result": result})
        elif kind == "CommandExecution":
            out.append({"t": "tool", "name": "shell", "input": it.get("command"), "result": it.get("aggregated_output")})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agent", choices=("claude", "codex"))
    ap.add_argument("project")
    ap.add_argument("--file", help="read this session file instead of the newest one")
    ap.add_argument("--tool", help="only tool calls whose name contains this")
    ap.add_argument("--say", action="store_true", help="only what the model wrote")
    ap.add_argument("--last", type=int, help="only the last N events left after filtering")
    args = ap.parse_args()
    path = Path(args.file) if args.file else (claude_file if args.agent == "claude" else codex_file)(args.project)
    print(f"# {path}", file=sys.stderr)
    events = (claude_events if args.agent == "claude" else codex_events)(path)
    if args.tool:
        events = [e for e in events if e["t"] == "tool" and args.tool in (e.get("name") or "")]
    if args.say:
        events = [e for e in events if e["t"] == "say"]
    for e in events[-args.last:] if args.last else events:
        print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
