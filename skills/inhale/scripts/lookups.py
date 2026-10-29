"""The advisory and malware lookups of the pre-install check, for a skill's files at its pinned commit.

install_skill.py --check calls check(). It reads the dependency files among the skill's files
(package-lock.json or package.json, uv.lock, requirements.txt, pyproject.toml), resolves versions a
lockfile does not give without installing or running anything (docs/adr/0004), and looks up:

- in OSV.dev: the dependencies at their versions, and the pinned commit itself (OSV matches a commit
  against the git ranges of its records). A record with a MAL- id comes from OpenSSF Malicious Packages:
  that is the malware lookup, and it blocks the install (docs/adr/0001). Any other record is a
  vulnerability: danger if it is critical or high, warn otherwise; any record for the commit is danger.
- on GitHub: the advisories the repo published for itself. Those OSV did not match to the commit are
  warn, as nobody can tell whether they affect it.

check_mcp.py calls check_package() instead, for an MCP server's published package: the subject is the
package at the version checked rather than a commit, and its dependencies are those resolving it brings.

A lookup that fails or runs out of time is reported as unchecked, never as nothing found.
"""
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

try:
    import tomllib
except ImportError:  # before Python 3.11: uv.lock and pyproject.toml cannot be read
    tomllib = None

OSV ="https://api.osv.dev/v1"
# All the lookups share this many seconds, inside the 120 the install tool gives the whole check.
BUDGET = 75
STEP = 30
BATCH = 1000
MAX_RECORDS = 200
SHOWN = 6
NOTED = 30
MAX_SOURCES = 10
SHOWN_SOURCES = 4
LOCKS = {"package-lock.json": "npm", "uv.lock": "PyPI"}
# The dependency files read when there is no lockfile beside them.
DEPENDENCY_FILES = {"package.json": "npm", "requirements.txt": "PyPI", "pyproject.toml": "PyPI"}
ADVISORY, MALWARE = "advisory lookup", "malware lookup"
DANGER_RATINGS = ("critical", "high")
RATINGS = ("critical", "high", "moderate", "low")
LABELS = {"critical": "critical", "high": "high", "moderate": "moderate", "medium": "moderate", "low": "low"}
NPM_DEPS = ("dependencies", "devDependencies", "optionalDependencies")
# OSV's ecosystem names as GitHub's advisories spell them.
GH_ECOSYSTEMS = {"npm": "npm", "PyPI": "pip"}
# Specs npm would fetch from somewhere other than the registry (git, a URL, a path, a GitHub shorthand).
NOT_REGISTRY = re.compile(r"^(git|https?:|file:|link:|github:|gitlab:|bitbucket:|gist:|[.~/])|^[^@\s]+/[^\s]+$")
ELSEWHERE = "some dependencies come from outside the npm registry, so versions were not resolved"
# Case-blind: older packages on the registry have upper-case names (JSONStream).
NPM_NAME = re.compile(r"^(@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9._~-]+$", re.I)
PY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
PY_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")


class Failed(Exception):
    """A lookup that could not run. The message says why, for the dialog."""


def shown(text, limit=100):
    """Text from a repo or a lookup, for the dialog and the model. Its author picks it, so invisible,
    control and line-breaking characters become ? and a long text is cut."""
    text = "".join("?" if unicodedata.category(ch)[0] == "C" or (ch.isspace() and ch != " ") else ch for ch in text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def first_line(text):
    return shown(next((l for l in text.splitlines() if l.strip()), "no output").strip(), 160)


class Net:
    """Everything the lookups reach outside this process; the tests put a fake in its place."""

    def __init__(self, budget=BUDGET):
        self.deadline = time.monotonic() + budget

    def timeout(self):
        left = self.deadline - time.monotonic()
        if left < 1:
            raise Failed("timed out")
        return min(STEP, left)

    def osv(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"{OSV}/{path}", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout()) as r:
                return json.load(r)
        except (OSError, ValueError) as e:
            raise Failed(f"OSV.dev: {first_line(str(e)) if str(e) else type(e).__name__}") from None

    def querybatch(self, queries):
        results = []
        for i in range(0, len(queries), BATCH):
            results += self.osv("querybatch", {"queries": queries[i:i + BATCH]}).get("results") or []
        if len(results) != len(queries):
            raise Failed("OSV.dev: an incomplete answer")
        return results

    def vuln(self, vid):
        return self.osv(f"vulns/{quote(vid)}")

    def advisories(self, repo):
        ok, out = self.run(["gh", "api", f"repos/{repo}/security-advisories?per_page=100"])
        if not ok:
            raise Failed(f"gh api: {first_line(out)}")
        try:
            return json.loads(out)
        except ValueError:
            raise Failed("gh api: not JSON") from None

    def which(self, name):
        return shutil.which(name) is not None

    def run(self, argv, cwd=None):
        try:
            r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               timeout=self.timeout())
        except (OSError, subprocess.TimeoutExpired, Failed) as e:
            return False, str(e) or "timed out"
        return r.returncode == 0, r.stdout if r.returncode == 0 else (r.stderr or r.stdout)


# ---- the dependency list ---------------------------------------------------------------------------

def py_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def package_key(ecosystem, name):
    """A package's name as its registry compares it: PyPI's normalised form, npm's in lower case."""
    return py_name(name) if ecosystem == "PyPI" else name.lower()


def sources(files):
    """The dependency files among the skill's files: per folder, the lockfile when there is one,
    otherwise the manifests."""
    by_dir = {}
    for rel in files:
        p = Path(rel)
        if "node_modules" not in p.parts and p.name in {**LOCKS, **DEPENDENCY_FILES}:
            by_dir.setdefault(p.parent, set()).add(p.name)
    picked = []
    for folder, names in sorted(by_dir.items()):
        for lockfile, manifests in (("package-lock.json", ["package.json"]), ("uv.lock", ["requirements.txt", "pyproject.toml"])):
            chosen = [lockfile] if lockfile in names else [m for m in manifests if m in names]
            picked += [str(folder / n) if str(folder) != "." else n for n in chosen]
    return picked


def npm_lock(data):
    found = set()
    packages = data.get("packages")
    if isinstance(packages, dict):
        for key, e in packages.items():
            if "node_modules/" in key and isinstance(e, dict) and not e.get("link") and isinstance(e.get("version"), str):
                found.add((e.get("name") or key.rsplit("node_modules/", 1)[1], e["version"]))
        return found

    def walk(deps):
        for name, e in (deps or {}).items():
            if isinstance(e, dict) and isinstance(e.get("version"), str):
                found.add((name, e["version"]))
                walk(e.get("dependencies"))
    walk(data.get("dependencies"))
    return found


def uv_lock(data):
    return {(py_name(p["name"]), p["version"]) for p in data.get("package") or []
            if isinstance(p, dict) and isinstance(p.get("version"), str) and "registry" in (p.get("source") or {})}


def requirement_names(lines):
    names = set()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        m = PY_NAME.match(line) if line and not line.startswith("-") and "://" not in line else None
        if m:
            names.add(py_name(m.group(1)))
    return names


def read(root, rel, net):
    """One dependency file as {file, ecosystem, packages: {(name, version)}, names: {name} whose version
    is unknown, resolved: whether the versions were resolved now, why: why the versions are unknown}."""
    path, name = root / rel, Path(rel).name
    ecosystem = LOCKS.get(name) or DEPENDENCY_FILES[name]
    src = {"file": rel, "ecosystem": ecosystem, "packages": set(), "names": set(), "resolved": False, "why": None}
    if tomllib is None and name in ("uv.lock", "pyproject.toml"):
        src.update(why="could not be read (needs Python 3.11 or later)", unreadable=True)
        return src
    try:
        text = path.read_text(errors="replace")
        if name == "package-lock.json":
            src["packages"] = npm_lock(json.loads(text))
            return src
        if name == "uv.lock":
            src["packages"] = uv_lock(tomllib.loads(text))
            return src
        if name == "package.json":
            data = json.loads(text)
            specs = {k: v for field in NPM_DEPS for k, v in (data.get(field) or {}).items()}
            src["names"] = {k for k in specs if NPM_NAME.match(k)}
            # npm would fetch those to resolve them, and a git dependency's prepare script can run then.
            elsewhere = [k for k, v in specs.items() if isinstance(v, str) and NOT_REGISTRY.match(v.strip())]
            if elsewhere:
                src["why"] = ELSEWHERE
        elif name == "requirements.txt":
            src["names"] = requirement_names(text.splitlines())
        else:
            project = tomllib.loads(text).get("project") or {}
            reqs = list(project.get("dependencies") or [])
            reqs += [r for group in (project.get("optional-dependencies") or {}).values() for r in group]
            src["names"] = requirement_names(r for r in reqs if isinstance(r, str))
    except (ValueError, AttributeError, TypeError) as e:  # TOMLDecodeError is a ValueError
        src["why"] = f"could not be read ({type(e).__name__})"
        src["unreadable"] = True
        return src
    if src["names"] and not src["why"]:
        resolve(root, rel, src, net)
    return src


def resolve(root, rel, src, net):
    """Fill in the versions the package manager would pick now, without installing or running anything."""
    tool = "npm" if src["ecosystem"] == "npm" else "uv"
    if not net.which(tool):
        src["why"] = f"{tool} not found, so versions were not resolved"
        return
    if tool == "npm":
        # Only package.json, in a folder of its own: the repo's .npmrc and the rest stay out of it.
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copyfile(root / rel, Path(tmp) / "package.json")
            ok, out = net.run(["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=tmp)
            lockfile = Path(tmp) / "package-lock.json"
            if ok and lockfile.is_file():
                try:
                    src["packages"] = npm_lock(json.loads(lockfile.read_text()))
                except ValueError:
                    ok, out = False, "the lockfile it wrote is not JSON"
    else:
        # --no-config keeps the repo's uv.toml or [tool.uv] (an index of its choosing, say) out of it.
        ok, out = net.run(["uv", "pip", "compile", "--no-build", "--no-config", "--quiet", "--no-header",
                           "--no-annotate", Path(rel).name], cwd=str((root / rel).parent))
        if ok:
            src["packages"] = {(py_name(m.group(1)), m.group(2)) for m in map(PY_PIN.match, out.splitlines()) if m}
    if not ok or not src["packages"]:
        src["why"] = f"{tool} could not resolve the versions: {first_line(out)}"
        src["packages"] = set()
        return
    src["resolved"] = True
    src["names"] = set()


# ---- ratings -----------------------------------------------------------------------------------------

def cvss3(vector):
    """The CVSS 3.x base score of a vector, or None if it is not one."""
    m = dict(part.split(":", 1) for part in vector.split("/")[1:] if ":" in part)
    w = {"AV": {"N": .85, "A": .62, "L": .55, "P": .2}, "AC": {"L": .77, "H": .44}, "UI": {"N": .85, "R": .62},
         "CIA": {"H": .56, "L": .22, "N": 0}}
    try:
        changed = {"U": False, "C": True}[m["S"]]
        pr = {"N": .85, "L": .68 if changed else .62, "H": .5 if changed else .27}[m["PR"]]
        iss = 1 - (1 - w["CIA"][m["C"]]) * (1 - w["CIA"][m["I"]]) * (1 - w["CIA"][m["A"]])
        reach = 8.22 * w["AV"][m["AV"]] * w["AC"][m["AC"]] * pr * w["UI"][m["UI"]]
    except KeyError:
        return None
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    score = min((1.08 if changed else 1) * (impact + reach), 10)
    n = round(score * 100000)
    return n / 100000 if n % 10000 == 0 else (math.floor(n / 10000) + 1) / 10


def rating(record):
    """critical, high, moderate or low, from the record's label or its CVSS 3 vector; None if neither."""
    label = (record.get("database_specific") or {}).get("severity")
    if isinstance(label, str) and label.lower() in LABELS:
        return LABELS[label.lower()]
    for s in record.get("severity") or []:
        score = cvss3(s.get("score") or "") if s.get("type") == "CVSS_V3" else None
        if score is not None:
            return "critical" if score >= 9 else "high" if score >= 7 else "moderate" if score >= 4 else "low"
    return None


def worst(ratings):
    known = [r for r in ratings if r]
    return min(known, key=RATINGS.index) if known else None


def groups(ids, records):
    """The ids OSV returned for one query, grouped so that a record and its aliases count once."""
    merged = []
    for vid in ids:
        group = {vid, *((records.get(vid) or {}).get("aliases") or [])}
        for other in [g for g in merged if g & group]:
            merged.remove(other)
            group |= other
        merged.append(group)
    order = {vid: i for i, vid in enumerate(ids)}
    out = []
    for g in merged:
        members = sorted((v for v in g if v in order), key=lambda v: (not v.startswith("GHSA-"), order[v]))
        out.append({"ids": members, "aliases": g, "rating": worst(rating(records.get(v) or {}) for v in members),
                    "summary": next((records[v]["summary"] for v in members if (records.get(v) or {}).get("summary")), "")})
    return sorted(out, key=lambda g: RATINGS.index(g["rating"]) if g["rating"] else len(RATINGS))


def listed(ids, limit=2):
    more = f", … (+{len(ids) - limit})" if len(ids) > limit else ""
    return ", ".join(ids[:limit]) + more


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


# ---- the check -----------------------------------------------------------------------------------------

def check(repo, sha, root, files, net=None):
    """The lookups for a skill: {"lines": the dialog's facts, "note": the same for the model, "blocked":
    whether the malware lookup found something, so Install is not offered, "found": whether either lookup
    found anything (each such finding is danger or warn), "nothing_found": when both
    lookups found nothing and nothing went unchecked, the dependencies they covered (for the one line
    install_skill.check_lines makes), else None}."""
    net = net or Net()
    found = sources(files)
    deps = [read(root, rel, net) for rel in found[:MAX_SOURCES]]
    # The files past the limit are not read, which the dialog says rather than leaving them out.
    rest = [shown(rel) for rel in found[MAX_SOURCES:]]
    unread = [(f"{plural(len(rest), 'more dependency file', 'more dependency files')} ({listed(rest)})",
               f"kirby reads at most {MAX_SOURCES}")] if rest else []
    return looked_up(repo, {"commit": sha}, "this commit", f"{repo} at commit {sha}", deps, net, unread=unread)


def check_package(repo, ecosystem, name, version, direct, net=None, why=None, elsewhere=False):
    """The lookups for an MCP server's published package (check_mcp.py), as check() gives them: the package
    itself at the version the install command is pinned to, and the packages it depends on, resolved as its
    package manager would resolve them now, without installing anything (docs/adr/0004). direct are the names
    it depends on, looked up by name for malware when the versions cannot be resolved. elsewhere: some of them
    come from outside the npm registry, so npm is not run, as read() does for a package.json. With version None
    (why says why it is not known), only the package itself is looked up, by name, for malware."""
    net = net or Net()
    what = f"{shown(name, 80)}@{shown(version, 40)}" if version else shown(name, 80)
    subject = f"the package {what} ({ecosystem})"
    query = {"package": {"name": name, "ecosystem": ecosystem}, **({"version": version} if version else {})}
    if version is None:
        return looked_up(repo, query, subject, subject, [], net, unknown=(f"the dependencies of {what}", why))
    own = name if ecosystem == "npm" else py_name(name)
    if elsewhere:
        src = {"ecosystem": ecosystem, "packages": set(), "names": set(), "resolved": False, "why": ELSEWHERE}
    else:
        with tempfile.TemporaryDirectory() as tmp:
            # A manifest of kirby's own that asks for just this package, so the tree is the one installing it brings.
            if ecosystem == "npm":
                rel = "package.json"
                text = json.dumps({"name": "kirby-check", "version": "0.0.0", "private": True, "dependencies": {name: version}})
            else:
                rel, text = "requirements.txt", f"{name}=={version}\n"
            (Path(tmp) / rel).write_text(text)
            src = read(Path(tmp), rel, net)
    src.update(file=what, part=f"the dependencies of {what}")
    src["packages"] = {(n, v) for n, v in src["packages"] if n != own}
    if not src["resolved"]:
        src["names"] = {n for n in (direct if ecosystem == "npm" else map(py_name, direct)) if n != own}
    return looked_up(repo, query, subject, subject, [src], net)


def looked_up(repo, query, subject, about, deps, net, unknown=None, unread=()):
    """The lookups of a subject (a commit, or a package; query is its OSV query) and of deps, as check()
    describes them. about names the subject for the model; unknown is (part, why) for dependencies that
    could not be listed at all; unread is (part, why) for each part of the dependencies that was not read."""
    findings, unchecked = [], []
    parts = {ADVISORY: [subject, "this repo's advisories"], MALWARE: [subject]}
    if unknown:
        part, why = unknown
        unchecked.append((ADVISORY, subject, why))
        unread = [*unread, unknown]
    for part, why in unread:
        parts[ADVISORY].append(part)
        parts[MALWARE].append(part)
        unchecked += [(ADVISORY, part, why), (MALWARE, part, why)]
    for d in deps:
        part = d.get("part", d["file"])
        parts[ADVISORY].append(part)
        parts[MALWARE].append(part)
        if d["why"]:
            unchecked.append((ADVISORY, part, d["why"]))
            if d.get("unreadable"):
                unchecked.append((MALWARE, part, d["why"]))

    versioned = sorted({(d["ecosystem"], n, v) for d in deps for n, v in d["packages"]})
    by_name = sorted({(d["ecosystem"], n) for d in deps for n in d["names"]} - {(e, n) for e, n, _ in versioned})
    queries = [query]
    queries += [{"package": {"name": n, "ecosystem": e}, "version": v} for e, n, v in versioned]
    queries += [{"package": {"name": n, "ecosystem": e}} for e, n in by_name]
    try:
        results = [[v["id"] for v in r.get("vulns") or [] if isinstance(v.get("id"), str)] for r in net.querybatch(queries)]
    except Failed as e:
        results = None
        for lookup in (ADVISORY, MALWARE):
            unchecked += [(lookup, part, str(e)) for part in parts[lookup] if part != "this repo's advisories"
                          and (lookup, part) not in {(u[0], u[1]) for u in unchecked}]

    commit_aliases = set()
    if results is not None:
        commit_ids, results = results[0], results[1:]
        if "version" not in query and "commit" not in query:  # a package by name: only a malware record says anything
            commit_ids = [v for v in commit_ids if v.startswith("MAL-")]
        wanted = {vid for ids in [commit_ids, *results[:len(versioned)]] for vid in ids if not vid.startswith("MAL-")}
        records, missed = full_records(sorted(wanted)[:MAX_RECORDS], net)
        missed += max(0, len(wanted) - MAX_RECORDS)
        if missed:
            unchecked.append((ADVISORY, f"the rating of {plural(missed, 'advisory', 'advisories')}",
                              "OSV.dev did not return the record"))
        findings += commit_findings(commit_ids, records, subject)
        commit_aliases = {a for g in groups([v for v in commit_ids if not v.startswith("MAL-")], records) for a in g["aliases"]}
        for (e, n, v), ids in zip(versioned, results):
            findings += package_findings(e, n, v, ids, records)
        for (e, n), ids in zip(by_name, results[len(versioned):]):
            findings += package_findings(e, n, None, [i for i in ids if i.startswith("MAL-")], {})

    try:
        package = (query["package"]["ecosystem"], query["package"]["name"]) if "package" in query else None
        findings += repo_findings(net.advisories(repo), commit_aliases, subject, package)
    except Failed as e:
        unchecked.append((ADVISORY, "this repo's advisories", str(e)))

    # Malware first, then the subject's own advisories, then the worst-rated dependencies.
    findings.sort(key=lambda f: (f["severity"] != "danger", f["lookup"] != MALWARE, f.get("rank", 0)))
    blocked = any(f["lookup"] == MALWARE for f in findings)
    none = "not known" if unknown else "no npm or Python dependency files"
    # Every lookup finding is danger or warn, so any of them is one the model review runs for (docs/adr/0002).
    return {"lines": dialog_lines(deps, findings, unchecked, parts, blocked, none),
            "note": note(about, deps, findings, unchecked, blocked, none), "blocked": blocked, "found": bool(findings),
            "nothing_found": None if findings or unchecked else covered(deps, versioned)}


def covered(deps, versioned):
    """The dependencies looked up, in a few words: "3 npm dependencies", "1 npm and 2 PyPI dependencies"."""
    if not deps:
        return "no npm or Python dependency files"
    ecosystems = list(dict.fromkeys(d["ecosystem"] for d in deps))
    counts = [sum(1 for e, _, _ in versioned if e == eco) for eco in ecosystems]
    return " and ".join(f"{n} {eco}" for n, eco in zip(counts, ecosystems)) + (" dependency" if sum(counts) == 1 else " dependencies")


def full_records(ids, net):
    """The full records of these ids, and how many could not be fetched."""
    def one(vid):
        try:
            return net.vuln(vid)
        except Failed:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        got = dict(zip(ids, pool.map(one, ids)))
    return {k: v for k, v in got.items() if isinstance(v, dict)}, sum(1 for v in got.values() if not isinstance(v, dict))


def package_findings(ecosystem, name, version, ids, records):
    what = f"{shown(name, 80)}@{shown(version, 40)}" if version else shown(name, 80)
    out = []
    bad = [v for v in ids if v.startswith("MAL-")]
    if bad:
        line = (f"danger: {what} ({ecosystem}) is a known-malicious package ({listed(bad)})" if version else
                f"danger: {what} ({ecosystem}) is listed as a malicious package ({listed(bad)}); matched by name, "
                "the version was not resolved")
        out.append({"severity": "danger", "lookup": MALWARE, "line": line, "what": f"{what} ({ecosystem})",
                    "notes": [f"danger malware {what} ({ecosystem}) {v}: in OpenSSF Malicious Packages" for v in bad]})
    vulns = groups([v for v in ids if not v.startswith("MAL-")], records)
    if vulns:
        severity = "danger" if vulns[0]["rating"] in DANGER_RATINGS else "warn"
        out.append({"severity": severity, "lookup": ADVISORY, "rank": rank(vulns[0]["rating"]),
                    "line": f"{severity}: {what} ({ecosystem}): {plural(len(vulns), 'vulnerability', 'vulnerabilities')}, "
                            f"worst {vulns[0]['rating'] or 'not rated'} ({listed([g['ids'][0] for g in vulns])})",
                    "notes": [f"{'danger' if g['rating'] in DANGER_RATINGS else 'warn'} advisory {what} ({ecosystem}) "
                              f"{described(g)}" for g in vulns]})
    return out


def rank(rated):
    return RATINGS.index(rated) if rated else len(RATINGS)


def described(group):
    """A group for the model: its id, rating and, if the record has one, its summary."""
    text = f"{group['ids'][0]} {group['rating'] or 'not rated'}"
    return f"{text}: {shown(group['summary'], 120)}" if group["summary"] else text


def commit_findings(ids, records, subject="this commit"):
    """The records for the subject itself (the pinned commit, or an MCP server's package at its version): any
    is danger, as it affects what installs."""
    out = []
    bad = [v for v in ids if v.startswith("MAL-")]
    if bad:
        out.append({"severity": "danger", "lookup": MALWARE, "what": subject,
                    "line": f"danger: {subject} is listed as malicious ({listed(bad)})",
                    "notes": [f"danger malware {subject} {v}: in OpenSSF Malicious Packages" for v in bad]})
    vulns = groups([v for v in ids if not v.startswith("MAL-")], records)
    if vulns:
        out.append({"severity": "danger", "lookup": ADVISORY, "rank": -1,
                    "line": f"danger: {subject} is affected by {plural(len(vulns), 'published vulnerability', 'published vulnerabilities')} "
                            f"({listed([g['ids'][0] for g in vulns])})",
                    "notes": [f"danger advisory {subject} {described(g)}" for g in vulns]})
    return out


def names_package(advisory, package):
    """Whether a repo advisory concerns package, (ecosystem, name): it names that package, or none at all."""
    if package is None:
        return True
    eco, name = package
    named = {((v.get("package") or {}).get("ecosystem"), (v.get("package") or {}).get("name"))
             for v in advisory.get("vulnerabilities") or [] if isinstance(v, dict) and isinstance(v.get("package"), dict)}
    return not named or any(e == GH_ECOSYSTEMS[eco] and isinstance(n, str) and package_key(eco, n) == package_key(eco, name)
                            for e, n in named)


def repo_findings(advisories, commit_aliases, subject="this commit", package=None):
    """The repo's own published advisories OSV did not place on the subject; for a package subject, only those
    that concern it (a repo can publish several packages)."""
    open_ = [a for a in advisories if isinstance(a, dict) and a.get("state") == "published" and not a.get("withdrawn_at")
             and isinstance(a.get("ghsa_id"), str) and not ({a["ghsa_id"], a.get("cve_id")} & commit_aliases)
             and names_package(a, package)]
    if not open_:
        return []
    named = [f"{shown(a['ghsa_id'], 40)} {shown(str(a.get('severity') or 'not rated'), 20)}" for a in open_]
    affect = "it affects" if len(open_) == 1 else "they affect"
    return [{"severity": "warn", "lookup": ADVISORY,
             "line": f"warn: this repo published {plural(len(open_), 'advisory', 'advisories')} ({listed(named)}); "
                     f"could not tell whether {affect} {subject}",
             "notes": [f"warn repo-advisory {n}: could not tell whether it affects {subject}" for n in named]}]


def deps_text(deps, none="no npm or Python dependency files"):
    if not deps:
        return f"dependencies: {none}"
    parts = []
    for d in deps:
        count = len(d["packages"]) or len(d["names"])
        how = (", could not be read" if d.get("unreadable") else ", versions resolved at check time" if d["resolved"]
               else ", names only" if d["names"] else "")
        parts.append(f"{shown(d['file'])}: {count} {d['ecosystem']}{how}")
    more = f"; … (+{len(parts) - SHOWN_SOURCES} files)" if len(parts) > SHOWN_SOURCES else ""
    return "dependencies: " + "; ".join(parts[:SHOWN_SOURCES]) + more


def unchecked_lines(unchecked, prefix):
    by_reason = {}
    for lookup, part, why in unchecked:
        by_reason.setdefault(why, {}).setdefault(lookup, []).append(shown(part))
    return [prefix + "; ".join(f"{lookup} for {', '.join(p)}" for lookup, p in per.items()) + f" ({why})"
            for why, per in by_reason.items()]


def dialog_lines(deps, findings, unchecked, parts, blocked, none):
    lines = [deps_text(deps, none)]
    if blocked:
        lines.append("blocked: the malware lookup found a known-malicious package, so Install is not offered")
    lines += [f["line"] for f in findings[:SHOWN]]
    rest = findings[SHOWN:]
    if rest:
        counts = {s: sum(1 for f in rest if f["severity"] == s) for s in ("danger", "warn")}
        lines.append("also: " + ", ".join(f"{n} {s}" for s, n in counts.items() if n) + " (listed for the model)")
    lines += unchecked_lines(unchecked, "unchecked: ")
    for lookup in (ADVISORY, MALWARE):
        if any(f["lookup"] == lookup for f in findings):
            continue
        missing = {u[1] for u in unchecked if u[0] == lookup}
        if not missing:
            lines.append(f"{lookup}: nothing found")
        elif set(parts[lookup]) - missing:
            lines.append(f"{lookup}: nothing found in the rest")
    return lines


def note(about, deps, findings, unchecked, blocked, none):
    """The lookups for the model, in every result after the dialog opens. about names what was looked up:
    "<repo> at commit <sha>" or the package."""
    notes = [n for f in findings for n in f["notes"]]
    if not notes and not unchecked:
        return (f"lookups: the dialog showed the user no findings from the advisory and malware lookups for {about}"
                f"\n{deps_text(deps, none)}")
    lines = [f"lookups: the dialog showed the user these advisory and malware lookup findings for {about}:"]
    lines += [f"  {n}" for n in notes[:NOTED]]
    if len(notes) > NOTED:
        lines.append(f"  … (+{len(notes) - NOTED} more)")
    lines += unchecked_lines(unchecked, "  unchecked: ")
    lines.append(deps_text(deps, none))
    if blocked:
        what = ", ".join(f["what"] for f in findings if f["lookup"] == MALWARE)
        lines.append(f"blocked: the dialog did not offer Install, because the malware lookup lists {what} as known-malicious. "
                     "kirby will not install it; tell the user why, and that installing it anyway means doing it by hand.")
    return "\n".join(lines)
