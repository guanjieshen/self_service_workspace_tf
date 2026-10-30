#!/usr/bin/env python3
"""Read-only checks that a workspace is ready for its first apply.

    scripts/preflight.py <workspace> [--out <file>]     (--out: also write the problems found to a file)

Signs in the way Terraform does (the Databricks CLI: in CI the pipeline's sign-in; locally
auth.workspace_profile from the workspace's file, or the CLI's default for the workspace's host)
and checks what Terraform needs but cannot fix itself:

  - the identity can sign in, and is a workspace admin;
  - the workspace has a Unity Catalog metastore;
  - every group the workspace names exists as an ACCOUNT group (Entra ID, synced to the account):
    Unity Catalog grants and usage policies cannot use workspace-local groups;
  - the platform admins group has members (nobody else can manage the workspace's usage
    policy, or even see it);
  - the identity may create the workspace's serverless usage policy (the account's Billing
    admin role; account admin alone is not enough);
  - the workspace catalog has somewhere to keep its data (a metastore storage root, or
    catalog.storage_root in the workspace's file);
  - before legacy access is disabled (one-way after 30 days): what still uses it.

Changes nothing. Prints ok / warning / error lines and exits 1 if there is an error. The
workspace's workflow runs it before every plan; run it yourself before onboarding a workspace.
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


# Values that must never reach a pull request comment or a file: JSON web tokens, and
# token=, secret= or password= values (the Databricks SDK lists its configuration,
# including the GitHub OIDC request token, in sign-in errors).
SECRETS = [re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"), re.compile(r"(?i)\b([\w-]*(?:token|secret|password)[\w-]*)=[^,\s]+")]


def redact(text):
    """text without anything that looks like a credential."""
    text = SECRETS[0].sub("***", text)
    return SECRETS[1].sub(lambda m: f"{m.group(1)}=***", text)


def short_error(text):
    """The CLI's error, first sentence only: what went wrong, without the configuration dump."""
    text = text.split(" Config: ", 1)[0].split(" Env: ", 1)[0]
    return redact(text.strip())[:300]


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
            return None, short_error((lines[-1] if lines else (r.stderr or r.stdout).strip()[-300:]).removeprefix("Error: "))
        try:
            return json.loads(r.stdout or "{}"), None
        except ValueError:
            return None, "not JSON: " + r.stdout[:200]
    return get


def checks(ws, get):
    """[(level, message)] for workspace ws; get(path) -> (json, error)."""
    f = wsf.ws_file(ws)
    info = wsf.workspace_info(f)
    prefix = info["prefix"]
    out = []

    # In CI, the pipeline signs in as the service principal named by the repository variables.
    # Empty ones mean the one-time setup is not done: say so, not "cannot sign in".
    if os.environ.get("GITHUB_ACTIONS") == "true":
        missing = [v for v in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID") if not os.environ.get(v.replace("AZURE_", "ARM_"))]
        if missing:
            return [("error", f"the repository variables {' and '.join(missing)} are not set, so the pipeline has no "
                              "identity to sign in with: do the one-time setup (docs/SETUP.md, steps 4 and 5: "
                              "scripts/setup.py identity, then scripts/setup.py github).")]
    me, err = get("/api/2.0/preview/scim/v2/Me")
    if err:
        return [("error", f"cannot sign in to {info['host']}: {err.rstrip('.')}. In CI: the service principal must be "
                          "workspace admin there (docs/SETUP.md, step 6), and the runner must reach the workspace "
                          "(its IP access list or Private Link: docs/github-actions.md). Locally: sign in with the "
                          "Azure or Databricks CLI.")]
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

    # Groups: in this workspace's file, or the baseline's (platform admins). A
    # persona without a group is skipped: nobody gets it here.
    for key in GROUP_KEYS:
        name = wsf.setting(f, "groups", key)
        if not name:
            out.append(("ok", f"no {key} group: skipped (nobody gets it in this workspace)"))
            continue
        name = name.replace("{prefix}", prefix).replace("{PREFIX}", prefix.upper())
        flt = urllib.parse.quote(f'displayName eq "{name}"')
        found, err = get(f"/api/2.0/account/scim/v2/Groups?filter={flt}&attributes=displayName,members")
        if err:
            out.append(("warning", f"could not look up group {name} in the account: {err}"))
        elif found.get("totalResults", 0) > 0:
            out.append(("ok", f"account group {name} ({key})"))
            # The platform admins manage the usage policy and own the catalog: an empty group
            # means only the pipeline can (people cannot even see the policy).
            if key == "platform_admins" and not any(g.get("members") for g in found.get("Resources", [])):
                out.append(("warning", f"group {name} (platform_admins) has no members, so nobody but the pipeline can "
                                       "manage the workspace's usage policy (or see it) or the catalog it owns: add the "
                                       "workspace's platform admins to it in Entra ID (docs/SETUP.md, step 7)"))
        else:
            local, _ = get(f"/api/2.0/preview/scim/v2/Groups?filter={flt}&attributes=displayName")
            what = ("exists only in this workspace (a workspace-local group)" if (local or {}).get("totalResults", 0)
                    else "does not exist in the account")
            out.append(("error", f"group {name} ({key}) {what}: create it in Entra ID and sync it to the account, "
                               f"or name another group under groups.{key} in the workspace's file"))

    if info.get("serverless_policy") and info.get("account"):
        out.append(billing_admin(get, info["account"], me, who))

    # The workspace catalog needs storage: the metastore's, or its own storage_root.
    if info["catalog"] and metastore is not None:
        existing, _ = get(f"/api/2.1/unity-catalog/catalogs/{info['catalog']}")
        if existing and existing.get("name"):
            out.append(("ok", f"catalog {info['catalog']} already exists"))
        elif not metastore.get("storage_root") and not wsf.setting(f, "catalog", "storage_root"):
            out.append(("error", f"the metastore has no storage root, so catalog {info['catalog']} needs one: set "
                                 "catalog.storage_root in the workspace's file to an external location's URL"))

    # Legacy access: once disabled for 30 days, the workspace is Unity Catalog only, for good.
    if wsf.setting(f, "settings", "disable_legacy_access") == "true":
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
                        "disable_legacy_access, disable_dbfs_root_and_mounts and enforce_user_isolation to null under settings: "
                        "in its file (config/workspaces/<name>.yaml)")]


def billing_admin(get, account, me, who):
    """Whether the identity may create usage policies: the account's Billing admin role, given to
    it or to one of its groups. Account admin alone fails with "missing CreateBudgetPolicyPermission"."""
    name = urllib.parse.quote(f"accounts/{account}/ruleSets/default")
    rules, err = get(f"/api/2.0/preview/accounts/access-control/rule-sets?name={name}&etag=")
    if err:
        return ("warning", f"could not check that {who} may create usage policies (the account's Billing admin role): {err}")
    me_id = me.get("userName") or ""
    mine = {f"servicePrincipals/{me_id}", f"users/{me_id}"} | {f"groups/{g.get('display')}" for g in me.get("groups", [])}
    billing = {p for r in rules.get("grant_rules", []) if r.get("role") == "roles/billing.admin" for p in r.get("principals", [])}
    if mine & billing:
        return ("ok", f"{who} may create usage policies (Billing admin)")
    # Only the pipeline's identity matters: locally (signed in as a person) it is a warning.
    level = "error" if os.environ.get("GITHUB_ACTIONS") == "true" else "warning"
    return (level, f"{who} cannot create the workspace's serverless usage policy: give the pipeline's service principal "
                   "the account's Billing admin role (account console > User management > Service principals > Roles; "
                   "account admin alone is not enough), docs/SETUP.md step 6, or set serverless_policy.enabled: false")


def main(argv):
    out_file = None
    if len(argv) == 3 and argv[1] == "--out":
        argv, out_file = argv[:1], argv[2]
    if len(argv) != 1 or argv[0].startswith("-"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    ws = argv[0]
    f = wsf.ws_file(ws)
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    profile = None if in_ci else wsf.nested(f, "auth", "workspace_profile")
    if not profile and not os.environ.get("DATABRICKS_HOST"):
        os.environ["DATABRICKS_HOST"] = wsf.workspace_info(f)["host"]
    results = checks(ws, cli_get(profile))
    for level, message in results:
        if in_ci and level != "ok":
            print(f"::{level}::{ws}: {message}")
        else:
            print(f"{level:8} {message}")
    if out_file:
        pathlib.Path(out_file).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out_file).write_text("".join(f"{l}: {redact(m)}\n" for l, m in results if l != "ok"))
        # Everything it checked, for the AI review: what it found clean is evidence too.
        out = pathlib.Path(out_file)
        everything = out.with_name(out.name.replace(".preflight.txt", ".preflight-all.txt")) if out.name.endswith(".preflight.txt") \
            else out.with_name(out.stem + "-all" + out.suffix)
        everything.write_text("".join(f"{l}: {redact(m)}\n" for l, m in results))
    errors = sum(1 for level, _ in results if level == "error")
    print(f"{ws}: {errors} error(s), {sum(1 for l, _ in results if l == 'warning')} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
