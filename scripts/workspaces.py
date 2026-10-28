#!/usr/bin/env python3
"""Everything about workspace folders: create one, find which a change affects, check them all.

    scripts/workspaces.py new <name> --bu <bu> --lob <LOB> --host <url> --account-id <id> [--catalog <catalog>]
                                          a workspace folder from config/workspaces/_example/
    scripts/workspaces.py changed [--plan] <base-ref> <head-ref>
    scripts/workspaces.py changed --all   the workspaces a change affects, as a JSON list (CI)
    scripts/workspaces.py check           checks across every workspace folder (CI)
    scripts/workspaces.py dir <ws>        the workspace's folder, relative to the repository
    scripts/workspaces.py field <ws> <key>  a top-level value of the workspace's workspace.yaml
    scripts/workspaces.py names '<json list>'  checks every name is a workspace folder (the Apply workflow)

Which workspaces a change affects:
  - a change to what Terraform does affects every workspace: config/defaults/, terraform/
    (not terraform/tests/), scripts/tf.sh and scripts/plan-guard.py;
  - with --plan (pull requests), so does a change to the AI review (scripts/ai-*.py,
    .github/ai/, config/ai-review.yaml) or to scripts/preflight.py, so the pull request shows
    the new review or checks;
  - otherwise, only the workspaces whose folder changed;
  - folders starting with "_" and workspaces with ci: false are never included.
Tests, docs and other scripts affect no workspace, so they never re-apply one.

Workspace folders are in config/workspaces/ (the organization's workspaces) and, in the
framework's own repository, dev/workspaces/ (the workspaces that test the framework; never
part of a release). A name must be unique across both.

Terraform validates one workspace at a time; some mistakes only show across workspaces,
because what they create is shared by the whole account or metastore:
  - two workspaces with the same host or id;
  - two workspaces creating a catalog with the same name (catalogs are per metastore);
  - two workspaces with the same bu on the same account, both managing budget policies:
    the policies are account-wide and named from bu ({BU}-SHARED, ...), so they collide;
  - a folder name that is not safe to use in workflow commands and environment names.
Standard library only: reads the simple YAML these files use (no anchors or flow maps).
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULTS = ROOT / "config/defaults"
WORKSPACES = ROOT / "config/workspaces"
DEV_WORKSPACES = ROOT / "dev/workspaces"
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def drop_comment(line):
    """The line without its trailing comment: a # after whitespace, outside quotes."""
    for m in re.finditer(r"\s#", line):
        before = line[:m.start()]
        if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
            return before.rstrip()
    return line.rstrip()


def lines_of(path):
    if not path.exists():
        return []
    return [drop_comment(l) for l in path.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]


def scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return None if value in ("", "null", "~") else value


def top_level(path):
    """Top-level `key: value` pairs (values of nested blocks are None)."""
    out = {}
    for l in lines_of(path):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", l)
        if m:
            out[m.group(1)] = scalar(m.group(2))
    return out


def block(path, key):
    """The indented lines under a top-level key."""
    out, inside = [], False
    for l in lines_of(path):
        if re.match(r"^\S", l):
            inside = re.match(rf"^{re.escape(key)}:\s*$", l) is not None
        elif inside:
            out.append(l)
    return out


def roots():
    return [WORKSPACES, DEV_WORKSPACES]


def ws_dir(ws):
    """The folder of workspace ws, in config/workspaces/ or dev/workspaces/."""
    if not NAME.match(ws):
        raise SystemExit(f"not a workspace folder name: {ws!r}")
    found = [r / ws for r in roots() if (r / ws / "workspace.yaml").exists()]
    if len(found) != 1:
        raise SystemExit(f"no workspace folder {ws}" if not found else
                         f"workspace {ws} is in both config/workspaces/ and dev/workspaces/: keep one")
    return found[0]


def field(ws, key):
    d = ws_dir(ws)
    value = top_level(d / "workspace.yaml").get(key)
    if value is None:
        raise SystemExit(f"{d.parent.parent.name}/{d.parent.name}/{ws}/workspace.yaml has no {key}")
    return value


def nested(path, section, key):
    """section.key from a file: the value under a top-level section."""
    return next((scalar(m.group(1)) for l in block(path, section)
                 for m in [re.match(rf"^\s{{2}}{key}:\s*(.*)$", l)] if m), None)


def workspace_info(d):
    ws = top_level(d / "workspace.yaml")
    bu = (ws.get("bu") or "").lower()
    host = (ws.get("host") or "").rstrip("/")
    # The catalog Terraform creates: the workspace's name, or the baseline's pattern
    # ({bu}_citizen_dev); none when the workspace sets catalog: null.
    if "catalog" in top_level(d / "catalog.yaml") and not block(d / "catalog.yaml", "catalog"):
        catalog = None
    else:
        catalog = nested(d / "catalog.yaml", "catalog", "name") or nested(DEFAULTS / "catalog.yaml", "catalog", "name")
        catalog = catalog.replace("{bu}", bu).replace("{BU}", bu.upper()) if catalog else None
    enabled = nested(d / "cost.yaml", "budget_policies", "enabled") or nested(DEFAULTS / "cost.yaml", "budget_policies", "enabled") or "true"
    workspace_id = ws.get("id") or next(iter(re.findall(r"adb-([0-9]+)\.", host)), None)
    return {"bu": bu, "account": ws.get("account_id"), "host": host,
            "id": workspace_id, "catalog": catalog, "budget_policies": enabled == "true"}


def names(listed, root=None):
    """The listed workspaces, each checked to be a workspace folder."""
    for n in listed:
        if not NAME.match(n):
            raise SystemExit(f"not a workspace folder name: {n!r}")
        if not root:
            ws_dir(n)
    return listed


def check(*dirs):
    """Problems across the workspace folders in dirs (default: config/ and dev/workspaces/)."""
    problems, seen = [], {}
    folders = sorted((d for root in (dirs or roots()) if root.is_dir() for d in root.iterdir()
                      if d.is_dir() and not d.name.startswith("_") and (d / "workspace.yaml").exists()),
                     key=lambda d: d.name)
    for d in folders:
        if not NAME.match(d.name):
            problems.append(f"{d.name}: folder names must be lowercase letters, digits, dashes and underscores "
                            "(they are used in workflow commands and environment names)")
            continue
        other = seen.setdefault(("name", d.name), d)
        if other != d:
            where = lambda x: f"{x.parent.parent.name}/{x.parent.name}/"
            problems.append(f"{d.name} is in both {where(other)} and {where(d)}: keep one")
            continue
        info = workspace_info(d)
        for key, what in (("host", "host"), ("id", "workspace id"), ("catalog", "catalog name")):
            value = info[key]
            if value:
                other = seen.setdefault((key, value), d.name)
                if other != d.name:
                    problems.append(f"{d.name} and {other} use the same {what} ({value})"
                                    + (": catalogs are shared by the metastore, so only one can create it" if key == "catalog" else ""))
        if info["budget_policies"] and info["bu"]:
            other = seen.setdefault(("bu", info["account"], info["bu"]), d.name)
            if other != d.name:
                problems.append(f"{d.name} and {other} both have bu {info['bu']} on account {info['account']} and manage "
                                f"budget policies, which are account-wide and named from bu ({info['bu'].upper()}-SHARED, ...): "
                                "give one a different bu, or set budget_policies: enabled: false in one's cost.yaml")
    return folders, problems


# ---- Which workspaces a change affects ----

EVERYTHING = r"^(config/defaults/|terraform/(?!tests/)|scripts/tf\.sh$|scripts/plan-guard\.py$)"
EVERYTHING_FOR_PLAN = EVERYTHING[:-1] + r"|scripts/ai-[^/]*\.py$|scripts/preflight\.py$|\.github/ai/|config/ai-review\.yaml$)"


def ci_workspaces():
    """Workspaces CI plans and applies: every folder but templates (_*) and ci: false."""
    out = []
    for root in roots():
        for d in sorted(root.glob("*/workspace.yaml")) if root.is_dir() else []:
            name = d.parent.name
            if not name.startswith("_") and (top_level(d).get("ci") or "true").lower() != "false":
                out.append(name)
    return sorted(out)


def changed(base, head, plan=False):
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if git("rev-parse", "--quiet", "--verify", f"{base}^{{commit}}").returncode != 0:
        return ci_workspaces()   # no usable base (first push, force push): everything
    prefix = git("rev-parse", "--show-prefix").stdout.strip()
    paths = [p[len(prefix):] if prefix and p.startswith(prefix) else p
             for p in git("diff", "--name-only", base, head, "--", ".").stdout.split("\n") if p]
    if any(re.match(EVERYTHING_FOR_PLAN if plan else EVERYTHING, p) for p in paths):
        return ci_workspaces()
    eligible = set(ci_workspaces())
    return sorted({m.group(2) for p in paths for m in [re.match(r"^(config|dev)/workspaces/([^/]+)/", p)]
                   if m and m.group(2) in eligible})


# ---- A new workspace folder ----

def new(name, bu, lob, host, account_id, catalog=None, root=ROOT):
    if not NAME.match(name):
        raise SystemExit("name must be lowercase letters, digits, dashes and underscores")
    src, dest = root / "config/workspaces/_example", root / "config/workspaces" / name
    if dest.exists():
        raise SystemExit(f"config/workspaces/{name}/ already exists")
    subs = [(r"(?m)^bu: xyz ", f"bu: {bu} "), (r"(?m)^lob: XYZ ", f"lob: {lob} "),
            (r"(?m)^account_id: .*", f"account_id: {account_id}"), (r"(?m)^host: .*", f"host: {host.rstrip('/')}"),
            (r"xyz-", f"{bu}-"), (r"xyz_citizen_dev", f"{bu}_citizen_dev")]
    if catalog:
        subs.append((r"(?m)^default_catalog: null .*", f"default_catalog: {catalog}"))
    for f in sorted(src.rglob("*")):
        target = dest / f.relative_to(src)
        if f.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        text = f.read_text()
        for pattern, repl in subs:
            text = re.sub(pattern, repl, text)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return dest


def main(argv):
    if argv[:1] == ["new"]:
        ap = argparse.ArgumentParser(prog="workspaces.py new")
        ap.add_argument("name")
        for a in ("--bu", "--lob", "--host", "--account-id"):
            ap.add_argument(a, required=True)
        ap.add_argument("--catalog")
        a = ap.parse_args(argv[1:])
        new(a.name, a.bu, a.lob, a.host, a.account_id, a.catalog)
        print(f"""Created config/workspaces/{a.name}/.

Next steps (docs/RUNBOOK.md, "Onboard a workspace"):
  1. The groups exist in Entra ID, synced to the Databricks account: {a.bu}_users, {a.bu}_explorer,
     {a.bu}_builder, {a.bu}_publisher, {a.bu}_platform_admins (or name others under groups: in access.yaml).
  2. The pipeline's service principal is workspace admin (a Databricks account admin):
     python3 scripts/setup.py databricks --client-id <AZURE_CLIENT_ID> {a.name}
  3. Review the other files; keep only what this workspace changes from the baseline.
  4. python3 scripts/preflight.py {a.name}     (read-only: is the workspace ready?)
  5. Open a pull request: its plan shows what the first apply does. Merge to apply.""")

        return 0
    if argv[:1] == ["changed"]:
        rest = argv[1:]
        if rest == ["--all"]:
            print(json.dumps(ci_workspaces()))
            return 0
        plan = rest[:1] == ["--plan"]
        rest = rest[1:] if plan else rest
        if len(rest) != 2:
            print(__doc__.split("\n\n")[1], file=sys.stderr)
            return 2
        print(json.dumps(changed(rest[0], rest[1], plan)))
        return 0
    if argv[:1] == ["check"]:
        folders, problems = check()
        for p in problems:
            print(f"::error::{p}" if "GITHUB_ACTIONS" in os.environ else f"error: {p}")
        print(f"{len(folders)} workspace folders checked, {len(problems)} problem(s).")
        return 1 if problems else 0
    if argv[:1] == ["dir"] and len(argv) == 2:
        print(ws_dir(argv[1]).relative_to(ROOT))
        return 0
    if argv[:1] == ["field"] and len(argv) == 3:
        print(field(argv[1], argv[2]))
        return 0
    if argv[:1] == ["names"] and len(argv) == 2:
        print(" ".join(names(json.loads(argv[1]))))
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
