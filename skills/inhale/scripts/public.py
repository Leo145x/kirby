#!/usr/bin/env python3
"""Search public GitHub repos for Claude Code skills, plugins and MCP servers.

    public.py "pdf"                       # any kind
    public.py "pdf OR document" --kind skill
    public.py "postgres" --kind mcp --min-stars 50

The query uses GitHub search syntax (words are ANDed; use OR between alternatives) and is
run once per topic that marks the wanted kind, e.g. `pdf topic:agent-skills`. Repo-level
search only sees each repo's name, description and topics, so a skill inside a large
multi-skill repo is found only if the repo itself is described that way.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOPICS = {
    "skill": ["agent-skills", "claude-skills", "claude-code-skills"],
    "plugin": ["claude-code-plugin", "claude-plugin"],
    "mcp": ["mcp-server", "model-context-protocol"],
}
TOPICS["any"] = [t for k in ("skill", "plugin", "mcp") for t in TOPICS[k]]
STARS_CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "kirby" / "stars.json"


def search(q):
    res = subprocess.run(["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={q}", "-f", "per_page=20"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return q, None, res.stderr.strip()
    return q, json.loads(res.stdout)["items"], None


def starred():
    try:
        return {r["repo"] for r in json.loads(STARS_CACHE.read_text())["repos"]}
    except (OSError, ValueError, KeyError):
        return set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help="GitHub search terms, e.g. 'pdf' or 'pdf OR document'")
    ap.add_argument("--kind", choices=TOPICS, default="any")
    ap.add_argument("--min-stars", type=int, default=10, help="skip repos below this star count (default 10)")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    queries = [f"{args.query} topic:{t} archived:false stars:>={args.min_stars}" for t in TOPICS[args.kind]]
    repos, errors = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for q, items, err in pool.map(search, queries):
            if err:
                errors.append(f"{q}: {err}")
                continue
            topic = q.split("topic:")[1].split()[0]
            for it in items:
                r = repos.setdefault(it["full_name"], {
                    "repo": it["full_name"],
                    "description": it["description"] or "",
                    "stars": it["stargazers_count"],
                    "pushedAt": (it["pushed_at"] or "")[:10],
                    "topics": it.get("topics") or [],
                    "matched": [],
                })
                r["matched"].append(topic)

    mine = starred()
    ranked = sorted(repos.values(), key=lambda r: -r["stars"])[:args.limit]
    for r in ranked:
        r["starredByYou"] = r["repo"] in mine

    for e in errors:
        print(f"warning: search failed: {e}", file=sys.stderr)
    if args.json:
        print(json.dumps(ranked, ensure_ascii=False, indent=1))
        return
    print(f"# {len(ranked)} of {len(repos)} public repos for {args.query!r} (kind={args.kind}, stars>={args.min_stars})")
    for r in ranked:
        yours = " [starred by you]" if r["starredByYou"] else ""
        print(f"{r['repo']} ★{r['stars']} · pushed {r['pushedAt'] or '?'}{yours} — {r['description'][:160]} "
              f"(matched: {','.join(r['matched'])})")


if __name__ == "__main__":
    main()
