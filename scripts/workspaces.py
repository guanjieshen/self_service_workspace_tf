#!/usr/bin/env python3
"""Everything about the workspace files: which workspaces a change concerns, and checks across them.

    scripts/workspaces.py affected --plan <base-ref> <head-ref>
    scripts/workspaces.py affected <base-ref> <head-ref>
                                          what a pull request plans (--plan) or a merge applies, as
                                          JSON: {"workspaces": [...], "removed": [...]}
    scripts/workspaces.py list            every workspace, as a JSON list (the drift check)
    scripts/workspaces.py check           checks across every workspace file (CI)
    scripts/workspaces.py field <ws> <key>  a top-level value of the workspace's file

A workspace is one file: config/workspaces/<name>.yaml (and, in the framework's own
repository, dev/workspaces/<name>.yaml, the workspaces that test the framework; never part
of a release). Files starting with "_" are templates. A name must be unique across both.

Which workspaces a change concerns:
  - a workspace's own file: that workspace (a deleted file: "removed", so its state goes);
  - what Terraform does to every workspace: all of them (config/defaults/, terraform/ but not
    its tests, scripts/tf.sh, scripts/plan-guard.py);
  - with --plan (pull requests), also what the plan comment shows: all of them, planned but
    never applied (scripts/preflight.py, scripts/ai-plan-review.py, .github/ai/,
    config/setup.yaml, the deploy workflow and what it uses);
  - anything else (tests, docs, other scripts): none.

Terraform validates one workspace at a time; some mistakes only show across workspaces,
because what they create is shared by the whole account or metastore:
  - two workspaces with the same host or id;
  - two workspaces creating a catalog with the same name (catalogs are per metastore);
  - two workspaces with the same prefix on the same account, both managing the serverless usage policy:
    the policies are account-wide and named from the prefix ({PREFIX}-0-SELF-SERVICE), so they collide;
  - a file name that is not safe to use in workflow commands and state file names.
Standard library only: reads the simple YAML these files use (no anchors or flow maps).
"""
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

# Paths whose change concerns every workspace: applied (EVERYTHING), or only planned (PLAN_ONLY).
# This file is one: it decides what is planned and applied, and reads each workspace's host.
EVERYTHING = r"^(config/defaults/|terraform/(?!tests/)|scripts/tf\.sh$|scripts/plan-guard\.py$|scripts/workspaces\.py$)"
# Under those paths, files Terraform never reads: guidance for maintainers (terraform/**.md) and
# loose files in the Genie Code skills folder (only skill folders are deployed, not its README).
NOT_DEPLOYED = r"^(terraform/.*\.md$|config/defaults/genie-code/skills/[^/]+$)"
PLAN_ONLY = (r"^(scripts/preflight\.py$|scripts/ai-plan-review\.py$|\.github/ai/|config/setup\.yaml$|"
             r"\.github/workflows/deploy\.yml$|\.github/actions/|\.github/scripts/plan-comment\.js$)")


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


def nested(path, section, key):
    """section.key from a file: the value under a top-level section."""
    return next((scalar(m.group(1)) for l in block(path, section)
                 for m in [re.match(rf"^\s{{2}}{key}:\s*(.*)$", l)] if m), None)


def defaults_file(section):
    """The baseline file that defines a top-level section, or None."""
    return next((f for f in sorted(DEFAULTS.glob("*.yaml")) if section in top_level(f)), None)


def setting(path, section, key):
    """section.key for workspace file `path`: its own value if it sets the key (even to null),
    else the baseline's. Returns the value, or None for null or missing."""
    for f in (path, defaults_file(section)):
        if f and any(re.match(rf"^\s{{2}}{re.escape(key)}:", l) for l in block(f, section)):
            return nested(f, section, key)
    return None


def roots():
    return [WORKSPACES, DEV_WORKSPACES]


def files(*dirs):
    """Every workspace file (not templates), sorted by name."""
    return sorted((f for root in (dirs or roots()) if root.is_dir() for f in root.glob("*.yaml")
                   if not f.name.startswith("_")), key=lambda f: f.stem)


def ws_file(ws):
    """The file of workspace ws: config/workspaces/<ws>.yaml or dev/workspaces/<ws>.yaml."""
    if not NAME.match(ws):
        raise SystemExit(f"not a workspace name: {ws!r}")
    found = [r / f"{ws}.yaml" for r in roots() if (r / f"{ws}.yaml").exists()]
    if len(found) != 1:
        raise SystemExit(f"no workspace file {ws}.yaml" if not found else
                         f"workspace {ws} is in both config/workspaces/ and dev/workspaces/: keep one")
    return found[0]


def field(ws, key):
    f = ws_file(ws)
    value = top_level(f).get(key)
    if value is None:
        raise SystemExit(f"{f.relative_to(ROOT) if f.is_relative_to(ROOT) else f} has no {key}")
    return value


def workspace_info(f):
    ws = top_level(f)
    prefix = (ws.get("prefix") or "").lower()
    host = (ws.get("host") or "").rstrip("/")
    # The catalog Terraform creates: the workspace's name, or the baseline's pattern
    # ({prefix}_citizen_dev); none when the workspace sets catalog: null.
    if "catalog" in ws and not block(f, "catalog"):
        catalog = None
    else:
        catalog = setting(f, "catalog", "name")
        catalog = catalog.replace("{prefix}", prefix).replace("{PREFIX}", prefix.upper()) if catalog else None
    enabled = setting(f, "serverless_policy", "enabled") or "true"
    workspace_id = ws.get("id") or next(iter(re.findall(r"adb-([0-9]+)\.", host)), None)
    account = ws.get("account_id") or top_level(defaults_file("account_id") or f).get("account_id")
    return {"prefix": prefix, "account": account, "host": host,
            "id": workspace_id, "catalog": catalog, "serverless_policy": enabled == "true"}


def check(*dirs):
    """Problems across the workspace files in dirs (default: config/ and dev/workspaces/)."""
    problems, seen = [], {}
    found = files(*dirs)
    for f in found:
        if not NAME.match(f.stem):
            problems.append(f"{f.name}: workspace file names must be lowercase letters, digits, dashes and "
                            "underscores (they are used in workflow commands and state file names)")
            continue
        other = seen.setdefault(("name", f.stem), f)
        if other != f:
            where = lambda x: f"{x.parent.parent.name}/{x.parent.name}/"
            problems.append(f"{f.stem} is in both {where(other)} and {where(f)}: keep one")
            continue
        info = workspace_info(f)
        for key, what in (("host", "host"), ("id", "workspace id"), ("catalog", "catalog name")):
            value = info[key]
            if value:
                other = seen.setdefault((key, value), f.stem)
                if other != f.stem:
                    problems.append(f"{f.stem} and {other} use the same {what} ({value})"
                                    + (": catalogs are shared by the metastore, so only one can create it" if key == "catalog" else ""))
        if info["serverless_policy"] and info["prefix"]:
            other = seen.setdefault(("prefix", info["account"], info["prefix"]), f.stem)
            if other != f.stem:
                problems.append(f"{f.stem} and {other} both have prefix {info['prefix']} on account {info['account']} and manage "
                                f"a serverless usage policy, which is account-wide and named from the prefix ({info['prefix'].upper()}-0-SELF-SERVICE): "
                                "give one a different prefix, or set serverless_policy: enabled: false in one's file")
    return found, problems


def names():
    return [f.stem for f in files()]


def affected(base, head, plan=False):
    """{"workspaces": what to plan or apply, "removed": workspaces whose file was deleted}."""
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    current = names()
    if git("rev-parse", "--quiet", "--verify", f"{base}^{{commit}}").returncode != 0:
        return {"workspaces": current, "removed": []}   # no usable base (first push, force push): everything
    prefix = git("rev-parse", "--show-prefix").stdout.strip()
    changes = [line.split("\t") for line in git("diff", "--name-status", "--no-renames", base, head, "--", ".").stdout.splitlines() if line]
    paths = [(status, p[len(prefix):] if prefix and p.startswith(prefix) else p) for status, p in changes]
    workspace_file = re.compile(r"^(config|dev)/workspaces/([^/_][^/]*)\.yaml$")
    removed = sorted({m.group(2) for status, p in paths for m in [workspace_file.match(p)]
                      if m and status == "D" and m.group(2) not in current})
    every = lambda p: re.match(EVERYTHING, p) and not re.match(NOT_DEPLOYED, p)
    if any(every(p) or (plan and re.match(PLAN_ONLY, p)) for _, p in paths):
        return {"workspaces": current, "removed": removed}
    touched = {m.group(2) for _, p in paths for m in [workspace_file.match(p)] if m}
    return {"workspaces": sorted(touched & set(current)), "removed": removed}


def main(argv):
    if argv[:1] == ["affected"]:
        rest = argv[1:]
        plan = rest[:1] == ["--plan"]
        rest = rest[1:] if plan else rest
        if len(rest) != 2:
            print(__doc__.split("\n\n")[1], file=sys.stderr)
            return 2
        print(json.dumps(affected(rest[0], rest[1], plan)))
        return 0
    if argv == ["list"]:
        print(json.dumps(names()))
        return 0
    if argv == ["check"]:
        found, problems = check()
        for p in problems:
            print(f"::error::{p}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"error: {p}")
        print(f"{len(found)} workspace files checked, {len(problems)} problem(s).")
        return 1 if problems else 0
    if argv[:1] == ["field"] and len(argv) == 3:
        print(field(argv[1], argv[2]))
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
