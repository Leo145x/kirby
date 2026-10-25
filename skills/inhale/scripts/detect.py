#!/usr/bin/env python3
"""Classify GitHub repos as Claude Code marketplace / plugin / skill / MCP server, and say how to install each.

    detect.py owner/repo [owner/repo ...]
    detect.py --match review lint -- owner/repo [owner/repo ...]

Reads the repo's file tree (one API call per repo) plus marketplace.json and SKILL.md
frontmatter where present. Nothing is installed. Descriptions are fetched for at most
15 skills per repo; with --match, skills whose path contains a term are fetched first.
"""
import argparse
import json
import re
import subprocess

MCP_FILES = ("server.json", "smithery.yaml", ".mcp.json", "mcp.json")
MCP_TOPICS = {"mcp", "mcp-server", "model-context-protocol", "mcp-servers"}
MAX_SKILLS = 15


def gh(*args):
    res = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def raw(repo, path):
    return gh(f"repos/{repo}/contents/{path}", "-H", "Accept: application/vnd.github.raw")


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text or "", re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            out[k.strip()] = v.strip().strip("\"'")
    return out


def plugin_has_mcp(repo, entry, paths):
    """Whether a marketplace plugin brings MCP servers; None when its source lives outside this repo."""
    if "mcpServers" in entry:
        return True
    src = entry.get("source")
    if not isinstance(src, str):
        return None
    base = src[2:] if src.startswith("./") else src
    base = base.strip("/")
    prefix = f"{base}/" if base else ""
    if f"{prefix}.mcp.json" in paths:
        return True
    manifest = f"{prefix}.claude-plugin/plugin.json"
    if manifest in paths:
        try:
            return "mcpServers" in json.loads(raw(repo, manifest) or "{}")
        except json.JSONDecodeError:
            return None
    return False


def detect(repo, terms=()):
    meta = gh(f"repos/{repo}")
    if meta is None:
        return {"repo": repo, "error": "not found or no access"}
    meta = json.loads(meta)
    tree = json.loads(gh(f"repos/{repo}/git/trees/HEAD?recursive=1") or '{"tree": []}')
    paths = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
    out = {"repo": repo, "description": meta.get("description") or "", "stars": meta.get("stargazers_count"),
           "pushedAt": (meta.get("pushed_at") or "")[:10], "archived": meta.get("archived", False),
           "kinds": [], "install": []}
    out["header"] = (f"{repo} ★{out['stars']} · pushed {out['pushedAt'] or '?'}"
                     + (" · ARCHIVED" if out["archived"] else ""))
    if tree.get("truncated"):
        out["note"] = "file tree truncated by GitHub; some skills may be missing"

    if ".claude-plugin/marketplace.json" in paths:
        out["kinds"].append("marketplace")
        try:
            mk = json.loads(raw(repo, ".claude-plugin/marketplace.json") or "{}")
        except json.JSONDecodeError:
            mk = {}
        for p in mk.get("plugins", []):
            out["install"].append({
                "type": "plugin",
                "name": p.get("name"),
                "description": p.get("description", ""),
                "mcpServers": plugin_has_mcp(repo, p, paths),
            })
    elif ".claude-plugin/plugin.json" in paths:
        out["kinds"].append("plugin-without-marketplace")

    skills = [p for p in paths if p == "SKILL.md" or p.endswith("/SKILL.md")]
    if skills:
        out["kinds"].append("skill")
        # Skills under dot-directories (.agents/, .claude/) are usually the repo's own dev tooling.
        def internal(p):
            return any(seg.startswith(".") for seg in p.split("/")[:-1])
        def matched(p):
            return any(t in p.lower() for t in terms)
        skills.sort(key=lambda p: (internal(p), not matched(p), p))
        for i, path in enumerate(skills):
            # Frontmatter costs one API call per skill, so only the first few get a description.
            fm = frontmatter(raw(repo, path)) if i < MAX_SKILLS else {}
            folder = path.rsplit("/", 1)[0] if "/" in path else ""
            out["install"].append({
                "type": "skill",
                "name": fm.get("name") or (folder.rsplit("/", 1)[-1] if folder else repo.split("/")[1]),
                "description": fm.get("description", "")[:300],
                "path": path,
                "internal": internal(path),
                "folder": folder or ".",
            })
        if len(skills) > MAX_SKILLS:
            out["note"] = f"{len(skills)} SKILL.md files; descriptions fetched for the first {MAX_SKILLS} only"

    topics = set(meta.get("topics") or [])
    mcp_files = [p for p in paths if p.rsplit("/", 1)[-1] in MCP_FILES and p.count("/") <= 1]
    if mcp_files or topics & MCP_TOPICS:
        out["kinds"].append("mcp")
        out["install"].append({
            "type": "mcp",
            "evidence": mcp_files or sorted(topics & MCP_TOPICS),
            "readme": f"gh api repos/{repo}/readme -H 'Accept: application/vnd.github.raw'",
        })

    if not out["kinds"]:
        out["kinds"].append("other")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="+", metavar="owner/repo")
    ap.add_argument("--match", nargs="+", default=[], metavar="TERM",
                    help="fetch descriptions first for skills whose path contains a term")
    args = ap.parse_args()
    terms = [t.lower() for t in args.match]
    print(json.dumps([detect(r, terms) for r in args.repos], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
