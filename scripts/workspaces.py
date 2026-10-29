#!/usr/bin/env python3
"""Everything about workspace folders: create one, keep its workflow, check them all.

    scripts/workspaces.py new <name> --bu <bu> --lob <LOB> --host <url> --account-id <id> [--catalog <catalog>]
                                          a workspace folder from config/workspaces/_example/,
                                          and its workflow, .github/workflows/workspace-<name>.yml
    scripts/workspaces.py workflows       (re)write every workspace's workflow from the template here
    scripts/workspaces.py check           checks across every workspace folder (CI)
    scripts/workspaces.py dir <ws>        the workspace's folder, relative to the repository
    scripts/workspaces.py field <ws> <key>  a top-level value of the workspace's workspace.yaml

Each workspace has its own workflow, which calls the shared one (.github/workflows/workspace.yml).
Its paths decide what plans and applies it: its own folder, and everything that changes what
Terraform does to every workspace (config/defaults/, terraform/ but not its tests, scripts/tf.sh,
scripts/plan-guard.py). A pull request also plans it for a change to what the plan comment
shows (scripts/preflight.py, the AI review). Tests, docs and other scripts plan nothing.

Workspace folders are in config/workspaces/ (the organization's workspaces) and, in the
framework's own repository, dev/workspaces/ (the workspaces that test the framework; never
part of a release). A name must be unique across both.

Terraform validates one workspace at a time; some mistakes only show across workspaces,
because what they create is shared by the whole account or metastore:
  - two workspaces with the same host or id;
  - two workspaces creating a catalog with the same name (catalogs are per metastore);
  - two workspaces with the same bu on the same account, both managing budget policies:
    the policies are account-wide and named from bu ({BU}-SHARED, ...), so they collide;
  - a folder name that is not safe to use in workflow commands and file names;
  - a workspace folder without its workflow, a workflow without its folder, or a workflow
    that differs from the template (run `workflows` to rewrite them).
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
WORKFLOWS = ROOT / ".github/workflows"
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


def workflow_text(name, folder):
    """The workflow of workspace `name`, whose folder is `folder` (relative to the repository)."""
    return f"""# The pipeline of workspace {name}: written by scripts/workspaces.py (`new`, or `workflows`
# to rewrite every workspace's). Edit the template there, not this file.
# A change to the workspace's folder, or to anything every workspace shares, plans it on the
# pull request and applies it on merge; the drift check runs every Monday.
name: "Workspace: {name}"

on:
  pull_request:
    paths:
      - "{folder}/**"
      - "config/defaults/**"
      - "terraform/**"
      - "!terraform/tests/**"
      - "scripts/tf.sh"
      - "scripts/plan-guard.py"
      - "scripts/preflight.py"
      - "scripts/ai-plan-review.py"
      - "config/setup.yaml"
      - ".github/ai/**"
      - ".github/actions/**"
      - ".github/scripts/plan-comment.js"
      - ".github/workflows/workspace.yml"
      - ".github/workflows/workspace-{name}.yml"
  push:
    branches: [main]
    paths:
      - "{folder}/**"
      - "config/defaults/**"
      - "terraform/**"
      - "!terraform/tests/**"
      - "scripts/tf.sh"
      - "scripts/plan-guard.py"
  schedule:
    - cron: "0 13 * * 1"     # drift check, Mondays 13:00 UTC
  workflow_dispatch:         # drift check, by hand

permissions:
  contents: read
  pull-requests: write       # the plan comment
  issues: write              # the drift issue
  id-token: write            # GitHub OIDC sign-in (Azure and Databricks)

jobs:
  workspace:
    uses: ./.github/workflows/workspace.yml
    with:
      workspace: {name}
"""


def write_workflow(d):
    path = WORKFLOWS / f"workspace-{d.name}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow_text(d.name, d.relative_to(ROOT).as_posix()))
    return path


def check(*dirs):
    """Problems across the workspace folders in dirs (default: config/ and dev/workspaces/)."""
    problems, seen = [], {}
    folders = sorted((d for root in (dirs or roots()) if root.is_dir() for d in root.iterdir()
                      if d.is_dir() and not d.name.startswith("_") and (d / "workspace.yaml").exists()),
                     key=lambda d: d.name)
    for d in folders:
        if not NAME.match(d.name):
            problems.append(f"{d.name}: folder names must be lowercase letters, digits, dashes and underscores "
                            "(they are used in workflow commands and file names)")
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
    if not dirs:   # the workflows: one per workspace folder, as the template writes it
        names = {d.name: d for d in folders}
        for d in folders:
            wf = WORKFLOWS / f"workspace-{d.name}.yml"
            if not wf.exists():
                problems.append(f"{d.name} has no workflow: run python3 scripts/workspaces.py workflows")
            elif wf.read_text() != workflow_text(d.name, d.relative_to(ROOT).as_posix()):
                problems.append(f"{wf.relative_to(ROOT)} differs from the template: run python3 scripts/workspaces.py workflows")
        for wf in sorted(WORKFLOWS.glob("workspace-*.yml")):
            if wf.stem[len("workspace-"):] not in names:
                problems.append(f"{wf.relative_to(ROOT)} has no workspace folder: delete it, or restore the folder")
    return folders, problems


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
        d = new(a.name, a.bu, a.lob, a.host, a.account_id, a.catalog)
        write_workflow(d)
        print(f"""Created config/workspaces/{a.name}/ and .github/workflows/workspace-{a.name}.yml.

Next steps (docs/SETUP.md, step 9):
  1. The groups exist in Entra ID, synced to the Databricks account: {a.bu}_users, {a.bu}_explorer,
     {a.bu}_builder, {a.bu}_publisher, {a.bu}_platform_admins (or name others under groups: in access.yaml).
  2. The pipeline's service principal is workspace admin there (by hand, a Databricks account
     admin: docs/SETUP.md, step 6).
  3. Review the other files; keep only what this workspace changes from the baseline.
  4. python3 scripts/preflight.py {a.name}     (read-only: is the workspace ready?)
  5. Open a pull request with both: its plan shows what the first apply does. Merge to apply.""")

        return 0
    if argv == ["workflows"]:
        folders, _ = check()
        for d in folders:
            print(write_workflow(d).relative_to(ROOT))
        for wf in sorted(WORKFLOWS.glob("workspace-*.yml")):
            if wf.stem[len("workspace-"):] not in {d.name for d in folders}:
                print(f"{wf.relative_to(ROOT)} has no workspace folder: delete it, or restore the folder")
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
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
