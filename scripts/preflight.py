#!/usr/bin/env python3
"""Read-only checks that a workspace is ready for its first apply.

    scripts/preflight.py <workspace> [--out <file>]     (--out: also write the problems found to a file)

Signs in the way Terraform does (the Databricks CLI: in CI the pipeline's sign-in; locally
auth.workspace_profile from workspace.yaml, or the CLI's default for the workspace's host)
and checks what Terraform needs but cannot fix itself:

  - the identity can sign in, and is a workspace admin;
  - the workspace has a Unity Catalog metastore;
  - every group set in access.yaml exists as an ACCOUNT group (Entra ID, synced to the account):
    Unity Catalog grants and usage policies cannot use workspace-local groups;
  - the workspace catalog has somewhere to keep its data (a metastore storage root, or
    catalog.storage_root in catalog.yaml);
  - before legacy access is disabled (one-way after 30 days): what still uses it;
  - placeholders in the baseline that must be replaced (the Git allowlist's <org>).

Changes nothing. Prints ok / warning / error lines and exits 1 if there is an error. The
Plan workflow runs it before every plan; run it yourself before onboarding a workspace.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspaces as wsf  # noqa: E402  (the same YAML reading as the other scripts)

GROUP_KEYS = ("users", "explorer", "builder", "publisher", "platform_admins")


def lookup(d, file, section, key):
    """section.key for workspace folder d: its own file if it sets the key (even to null),
    else the baseline's. Returns the value, or None for null or missing."""
    for path in (d / file, wsf.DEFAULTS / file):
        if any(re.match(rf"^\s{{2}}{re.escape(key)}:", l) for l in wsf.block(path, section)):
            return wsf.nested(path, section, key)
    return None


def cli_get(profile):
    """GET a workspace API path with the Databricks CLI; returns (json, None) or (None, error)."""
    def get(path):
        cmd = ["databricks", "api", "get", path, "-o", "json"] + (["--profile", profile] if profile else [])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise SystemExit("error: the Databricks CLI (databricks) is not installed")
        except subprocess.TimeoutExpired:
            return None, "timed out"
        if r.returncode != 0:
            lines = [l for l in (r.stderr or r.stdout).splitlines() if l.startswith("Error")]
            return None, (lines[-1] if lines else (r.stderr or r.stdout).strip()[-300:]).removeprefix("Error: ")
        try:
            return json.loads(r.stdout or "{}"), None
        except ValueError:
            return None, "not JSON: " + r.stdout[:200]
    return get


def checks(ws, get):
    """[(level, message)] for workspace folder ws; get(path) -> (json, error)."""
    d = wsf.ws_dir(ws)
    info = wsf.workspace_info(d)
    bu = info["bu"]
    out = []

    me, err = get("/api/2.0/preview/scim/v2/Me")
    if err:
        return [("error", f"cannot sign in to {info['host']}: {err}. In CI: the service principal must be "
                          "added to the workspace, and the runner must be allowed through its IP access list or "
                          "Private Link (docs/github-actions.md). Locally: sign in with the Azure or Databricks CLI.")]
    who = me.get("userName") or me.get("displayName") or "this identity"
    if "admins" in {g.get("display") for g in me.get("groups", [])}:
        out.append(("ok", f"signed in as {who}, a workspace admin"))
    else:
        out.append(("error", f"{who} is not a workspace admin: make it one (docs/SETUP.md, step 6)"))

    assignment, err = get("/api/2.1/unity-catalog/current-metastore-assignment")
    metastore = None
    if err or not assignment.get("metastore_id"):
        out.append(("error", f"no Unity Catalog metastore is assigned to the workspace ({err or 'none'})"))
    else:
        metastore, err = get(f"/api/2.1/unity-catalog/metastores/{assignment['metastore_id']}")
        out.append(("ok", f"metastore {(metastore or {}).get('name', assignment['metastore_id'])}"))

    # Groups: in this workspace's access.yaml, or the baseline's (platform admins). A
    # persona without a group is skipped: nobody gets it here.
    for key in GROUP_KEYS:
        name = lookup(d, "access.yaml", "groups", key)
        if not name:
            out.append(("ok", f"no {key} group: skipped (nobody gets it in this workspace)"))
            continue
        name = name.replace("{bu}", bu).replace("{BU}", bu.upper())
        flt = urllib.parse.quote(f'displayName eq "{name}"')
        found, err = get(f"/api/2.0/account/scim/v2/Groups?filter={flt}&attributes=displayName")
        if err:
            out.append(("warning", f"could not look up group {name} in the account: {err}"))
        elif found.get("totalResults", 0) > 0:
            out.append(("ok", f"account group {name} ({key})"))
        else:
            local, _ = get(f"/api/2.0/preview/scim/v2/Groups?filter={flt}&attributes=displayName")
            what = ("exists only in this workspace (a workspace-local group)" if (local or {}).get("totalResults", 0)
                    else "does not exist in the account")
            out.append(("error", f"group {name} ({key}) {what}: create it in Entra ID and sync it to the account, "
                               f"or name another group under groups.{key} in access.yaml"))

    # The workspace catalog needs storage: the metastore's, or its own storage_root.
    if info["catalog"] and metastore is not None:
        existing, _ = get(f"/api/2.1/unity-catalog/catalogs/{info['catalog']}")
        if existing and existing.get("name"):
            out.append(("ok", f"catalog {info['catalog']} already exists"))
        elif not metastore.get("storage_root") and not lookup(d, "catalog.yaml", "catalog", "storage_root"):
            out.append(("error", f"the metastore has no storage root, so catalog {info['catalog']} needs one: set "
                                 "catalog.storage_root in catalog.yaml to an external location's URL"))

    # The baseline ships with placeholders to replace: a Git allowlist of github.com/<org>/
    # allows nothing that exists.
    for path in (d / "settings.yaml", wsf.DEFAULTS / "settings.yaml"):
        lines = wsf.block(path, "settings")
        if any("allowed_urls" in l for l in lines):
            if any("<org>" in l for l in lines):
                out.append(("warning", f"the Git allowlist (settings.git.allowed_urls in {path.parent.name}/settings.yaml) "
                                       "still has the placeholder https://github.com/<org>/: replace it with your organization's URL"))
            break

    # Legacy access: once disabled for 30 days, the workspace is Unity Catalog only, for good.
    if lookup(d, "settings.yaml", "settings", "disable_legacy_access") == "true":
        current, _ = get("/api/2.1/settings/disable_legacy_access")
        if ((current or {}).get("disable_legacy_access") or (current or {}).get("effective_boolean_val") or {}).get("value"):
            out.append(("ok", "legacy access is already disabled"))
        else:
            out.extend(legacy_uses(get))
    return out


def legacy_uses(get):
    found = []
    schemas, err = get("/api/2.1/unity-catalog/schemas?catalog_name=hive_metastore&max_results=50")
    if not err:
        names = [s["name"] for s in schemas.get("schemas", []) if s.get("name") not in ("default", "information_schema")]
        if names:
            found.append(f"Hive metastore schemas: {', '.join(names[:10])}")
    mounts, err = get("/api/2.0/dbfs/list?path=/mnt")
    if not err and mounts.get("files"):
        found.append(f"DBFS mounts: {', '.join(f['path'] for f in mounts['files'][:10])}")
    clusters, _ = get("/api/2.1/clusters/list?page_size=100")
    legacy = [c.get("cluster_name", c.get("cluster_id")) for c in (clusters or {}).get("clusters", [])
              if c.get("data_security_mode") in ("NONE", "LEGACY_PASSTHROUGH", "LEGACY_TABLE_ACL", "LEGACY_SINGLE_USER")]
    if legacy:
        found.append(f"clusters without Unity Catalog access modes: {', '.join(legacy[:10])}")
    if not found:
        return [("ok", "nothing found that still uses legacy access (Hive metastore, DBFS mounts, legacy clusters)")]
    return [("warning", "the baseline disables legacy access, which becomes permanent after 30 days, and this "
                        "workspace still has " + "; ".join(found) + ". Migrate them first, or set "
                        "disable_legacy_access: null and disable_dbfs_root_and_mounts: null under settings: in its settings.yaml")]


def main(argv):
    out_file = None
    if len(argv) == 3 and argv[1] == "--out":
        argv, out_file = argv[:1], argv[2]
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    ws = argv[0]
    d = wsf.ws_dir(ws)
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    profile = None if in_ci else wsf.nested(d / "workspace.yaml", "auth", "workspace_profile")
    if not profile and not os.environ.get("DATABRICKS_HOST"):
        os.environ["DATABRICKS_HOST"] = wsf.workspace_info(d)["host"]
    results = checks(ws, cli_get(profile))
    for level, message in results:
        if in_ci and level != "ok":
            print(f"::{level}::{ws}: {message}")
        else:
            print(f"{level:8} {message}")
    if out_file:
        pathlib.Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out_file).write_text("".join(f"{l}: {m}\n" for l, m in results if l != "ok"))
    errors = sum(1 for level, _ in results if level == "error")
    print(f"{ws}: {errors} error(s), {sum(1 for l, _ in results if l == 'warning')} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
