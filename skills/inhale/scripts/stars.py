#!/usr/bin/env python3
"""Print an index of the viewer's GitHub stars, annotated with the star lists each repo is in.

Data comes from the GitHub GraphQL API through `gh` and is cached for 24 hours.

    stars.py                      # every starred repo
    stars.py --list ai-tools      # only repos in one list (name or slug)
    stars.py --match pdf review   # repos whose name/description/topics/lists contain any term
    stars.py --lists              # just the list names and sizes
    stars.py --refresh            # ignore the cache
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "kirby" / "stars.json"
TTL = 24 * 3600

STARS_Q = """
query($endCursor: String) {
  viewer {
    starredRepositories(first: 100, after: $endCursor, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner description stargazerCount pushedAt isArchived
        repositoryTopics(first: 20) { nodes { topic { name } } }
      }
    }
  }
}"""

LISTS_Q = """
query {
  viewer { login lists(first: 100) { nodes { id name slug description isPrivate } } }
}"""

ITEMS_Q = """
query($id: ID!, $endCursor: String) {
  node(id: $id) {
    ... on UserList {
      items(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { ... on Repository { nameWithOwner description stargazerCount pushedAt isArchived
                                    repositoryTopics(first: 20) { nodes { topic { name } } } } }
      }
    }
  }
}"""


def gql(query, paginate=False, **variables):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-f", f"{k}={v}"]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"gh api graphql failed: {res.stderr.strip()}\nIs `gh auth login` done?")
    data = json.loads(res.stdout)
    return data if paginate else [data]


def fetch():
    def entry(n):
        return {
            "repo": n["nameWithOwner"],
            "description": n["description"] or "",
            "stars": n["stargazerCount"],
            "pushedAt": (n["pushedAt"] or "")[:10],
            "archived": n["isArchived"],
            "topics": [t["topic"]["name"] for t in n["repositoryTopics"]["nodes"]],
            "lists": [],
        }

    repos = {}
    for page in gql(STARS_Q, paginate=True):
        for n in page["data"]["viewer"]["starredRepositories"]["nodes"]:
            repos[n["nameWithOwner"]] = entry(n)

    viewer = gql(LISTS_Q)[0]["data"]["viewer"]
    lists = []
    for lst in viewer["lists"]["nodes"]:
        members = []
        for page in gql(ITEMS_Q, paginate=True, id=lst["id"]):
            members += [n for n in page["data"]["node"]["items"]["nodes"] if n]
        lists.append({k: lst[k] for k in ("name", "slug", "description", "isPrivate")} | {"count": len(members)})
        for n in members:
            # A list can hold a repo the viewer has since unstarred; keep it, it was curated on purpose.
            repos.setdefault(n["nameWithOwner"], entry(n))["lists"].append(lst["name"])

    return {"login": viewer["login"], "fetchedAt": time.time(), "lists": lists, "repos": list(repos.values())}


def load(refresh):
    if not refresh and CACHE.exists():
        data = json.loads(CACHE.read_text())
        if time.time() - data.get("fetchedAt", 0) < TTL:
            return data
    data = fetch()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", help="only repos in this star list (name or slug, case-insensitive)")
    ap.add_argument("--match", nargs="+", metavar="TERM", help="keep repos matching any term")
    ap.add_argument("--lists", action="store_true", help="print the star lists only")
    ap.add_argument("--refresh", action="store_true", help="refetch instead of using the cache")
    ap.add_argument("--json", action="store_true", help="print JSON instead of one line per repo")
    args = ap.parse_args()

    data = load(args.refresh)
    age = int((time.time() - data["fetchedAt"]) / 60)

    if args.lists:
        for lst in data["lists"]:
            private = " (private)" if lst["isPrivate"] else ""
            print(f"{lst['name']} [{lst['slug']}] {lst['count']} repos{private} {lst['description'] or ''}".rstrip())
        return

    repos = data["repos"]
    if args.list:
        want = args.list.lower()
        names = {l["name"] for l in data["lists"] if want in (l["name"].lower(), l["slug"].lower())}
        if not names:
            sys.exit(f"no star list named {args.list!r}; have: {', '.join(l['slug'] for l in data['lists'])}")
        repos = [r for r in repos if names & set(r["lists"])]
    if args.match:
        terms = [t.lower() for t in args.match]
        def hay(r):
            return " ".join([r["repo"], r["description"], *r["topics"], *r["lists"]]).lower()
        repos = [r for r in repos if any(t in hay(r) for t in terms)]

    if args.json:
        print(json.dumps(repos, ensure_ascii=False, indent=1))
        return
    print(f"# {len(repos)} of {len(data['repos'])} repos for {data['login']} (cache age {age} min)")
    for r in repos:
        lists = f" [{', '.join(r['lists'])}]" if r["lists"] else ""
        topics = f" (topics: {','.join(r['topics'])})" if r["topics"] else ""
        archived = " · ARCHIVED" if r["archived"] else ""
        print(f"{r['repo']} ★{r['stars']} · pushed {r['pushedAt'] or '?'}{archived}{lists} — "
              f"{r['description']}{topics}")


if __name__ == "__main__":
    main()
