#!/usr/bin/env python3
"""Flag changes in a Terraform plan that are hard or impossible to undo, or that weaken security.

Reads `terraform show -json <plan>` on stdin. Prints a warning for each risky
change and exits 2 if there is any, 0 otherwise.

    scripts/plan-guard.py [--preflight .plans/<workspace>.preflight-all.txt] < plan.json

Disabling legacy access is one-way, but on a workspace where it is not managed yet (a
first apply) it is not flagged when preflight found nothing that still uses legacy
access: that is the case for every new workspace. Without that finding (preflight found
something, or did not run) it is flagged as usual.

A planned deletion of something the workspace now leaves unmanaged (the
released_addresses output) is not risky: scripts/tf.sh removes it from the state
before apply, so the workspace keeps its current value. It is listed as a release.
"""
import argparse
import json
import pathlib
import sys

# Objects people build on. Deleting or replacing them loses work, IDs or access.
PROTECTED = {
    "databricks_directory": "folder (and everything in it)",
    "databricks_budget_policy": "budget policy (jobs and notebooks lose it; new policy ID)",
    "databricks_access_control_rule_set": "budget policy access",
    "databricks_sql_endpoint": "SQL warehouse (new ID; dashboards and alerts using it break)",
    "databricks_cluster": "cluster (new ID; jobs and notebooks attached to it break)",
    "databricks_cluster_policy": "cluster policy (clusters using it lose their policy)",
    "databricks_permission_assignment": "group's access to the workspace",
    "databricks_entitlements": "group entitlements",
    "databricks_workspace_conf": "workspace configuration (enable*/enforce* keys reset to false)",
    "databricks_catalog": "catalog (and every table, view and volume in it)",
    "databricks_schema": "schema (and every table, view and volume in it)",
    "databricks_grants": "catalog or schema grants (everyone listed loses that access)",
    "databricks_permissions": "permissions (everyone listed loses that access)",
}


# Security settings: how to read the value, and the value that is the secure one.
# Deleting one returns it to the platform default (less secure); so does changing it.
SECURITY_SETTINGS = {
    "databricks_disable_legacy_access_setting": ("disable legacy access", lambda v: one(v, "disable_legacy_access").get("value"), True),
    "databricks_disable_legacy_dbfs_setting": ("disable DBFS root and mounts", lambda v: one(v, "disable_legacy_dbfs").get("value"), True),
    "databricks_restrict_workspace_admins_setting": ("restrict workspace admins", lambda v: one(v, "restrict_workspace_admins").get("status"), "RESTRICT_TOKENS_AND_JOB_RUN_AS"),
    "databricks_enhanced_security_monitoring_workspace_setting": ("enhanced security monitoring", lambda v: one(v, "enhanced_security_monitoring_workspace").get("is_enabled"), True),
}
# databricks_workspace_setting_v2 is one resource type for many settings, told apart by name.
SECURITY_SETTINGS_V2 = {
    "enforce_ai_gateway_v3_only": ("Enforce Unity Gateway", lambda v: (v.get("boolean_val") or {}).get("value"), True),
    "sql_results_download": ("block SQL results download", lambda v: (v.get("boolean_val") or {}).get("value"), False),
    "collaboration_platform_connectivity": ("block collaboration platforms",
                                            lambda v: (v.get("collaboration_platform_connectivity") or {}).get("connectivity"), "DENY_ALL"),
    "collaboration_platform_message_visibility": ("private collaboration platform answers",
                                                  lambda v: (v.get("boolean_val") or {}).get("value"), False),
}
# Workspace configuration keys and their secure value; a change away from it loosens security.
SECURE_CONF = {
    "enforceUserIsolation": "true", "enableProjectsAllowList": "true", "enableVerboseAuditLogs": "true",
    "enableTokensConfig": "false", "enableResultsDownloading": "false", "enableExportNotebook": "false",
    "enableNotebookTableClipboard": "false", "enableWebTerminal": "false", "enableDbfsFileBrowser": "false",
    "mlflowRunArtifactDownloadEnabled": "false", "enableUploadDataUis": "false",
}
EVERYONE = {"account users", "users"}
# The line scripts/preflight.py writes when nothing uses legacy access (scripts/tests/ checks they match).
NOTHING_USES_LEGACY = "ok: nothing found that still uses legacy access"


def one(values, block):
    """The first (only) element of a nested block, or {}."""
    items = (values or {}).get(block) or [{}]
    return items[0] if isinstance(items, list) else items


def grantees(values):
    return {g.get("principal") for g in (values or {}).get("grant") or []}


def token_groups(values):
    return {a.get("group_name") for a in (values or {}).get("access_control") or []}


def loosened(rc):
    """Plain-language warnings for a change that weakens security (not for first-time creation)."""
    actions, rtype = rc["change"]["actions"], rc["type"]
    before, after = rc["change"].get("before") or {}, rc["change"].get("after") or {}
    out = []
    setting = SECURITY_SETTINGS.get(rtype)
    if rtype == "databricks_workspace_setting_v2":
        setting = SECURITY_SETTINGS_V2.get(before.get("name") or after.get("name"))
    if setting and "create" not in actions:
        name, read, secure = setting
        if "delete" in actions and read(before) == secure:
            out.append(f"TURN OFF {name}: Terraform stops managing it and it returns to the platform default")
        elif read(before) == secure and read(after) != secure:
            out.append(f"TURN OFF {name}")
    if rtype == "databricks_workspace_conf" and actions == ["update"]:
        b, a = before.get("custom_config") or {}, after.get("custom_config") or {}
        for key, secure in SECURE_CONF.items():
            if b.get(key) == secure and key in a and a[key] != secure:
                out.append(f"LOOSEN workspace setting {key}: {b[key]} -> {a[key]}")
        if b.get("maxTokenLifetimeDays") and a.get("maxTokenLifetimeDays") and int(a["maxTokenLifetimeDays"]) > int(b["maxTokenLifetimeDays"]):
            out.append(f"LOOSEN maximum token lifetime: {b['maxTokenLifetimeDays']} -> {a['maxTokenLifetimeDays']} days")
    if rtype == "databricks_catalog" and before.get("isolation_mode") == "ISOLATED" and after.get("isolation_mode") == "OPEN":
        out.append(f"OPEN catalog {after.get('name')} to every workspace on the metastore (was this workspace only)")
    if rtype == "databricks_grants" and "delete" not in actions:
        new = (grantees(after) - grantees(before)) & EVERYONE
        if new:
            on = after.get("catalog") or after.get("schema") or "an object"
            out.append(f"GRANT {', '.join(sorted(new))} (everyone) privileges on {on}")
    if rtype == "databricks_permissions" and after.get("authorization") == "tokens" and actions == ["update"]:
        new = token_groups(after) - token_groups(before)
        if new:
            out.append(f"WIDEN who may create personal access tokens: adds {', '.join(sorted(new))}")
    if rtype == "databricks_entitlements" and rc["address"].endswith(".users[0]") and actions == ["update"]:
        if not before.get("allow_cluster_create") and after.get("allow_cluster_create"):
            out.append("GIVE every user unrestricted cluster creation (users group)")
    return out


def released(plan):
    """The released_addresses output: addresses (resources, or modules) to release."""
    out = ((plan.get("planned_values") or {}).get("outputs") or {}).get("released_addresses") or {}
    return out.get("value") or []


def is_released(addr, prefixes):
    return any(addr == p or addr.startswith(p + ".") or addr.startswith(p + "[") for p in prefixes)


def nothing_uses_legacy(preflight_file):
    """Whether preflight found nothing that still uses legacy access."""
    try:
        return any(l.startswith(NOTHING_USES_LEGACY) for l in pathlib.Path(preflight_file).read_text().splitlines())
    except (OSError, TypeError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Flag hard-to-undo or security-weakening changes in a plan (JSON on stdin).")
    ap.add_argument("--preflight", help="preflight's findings (.plans/<workspace>.preflight-all.txt)")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    plan = json.load(sys.stdin)
    warnings: list[str] = []
    notes: list[str] = []
    releases: list[str] = []
    prefixes = released(plan)

    for rc in plan.get("resource_changes", []):
        actions = rc["change"]["actions"]
        rtype, addr = rc["type"], rc["address"]

        if actions == ["delete"] and is_released(addr, prefixes):
            releases.append(addr)
            continue

        warnings.extend(f"{w}\n      {addr}" for w in loosened(rc))

        if "delete" in actions and rtype in PROTECTED:
            verb = "REPLACE" if "create" in actions else "DELETE"
            warnings.append(f"{verb} {PROTECTED[rtype]}\n      {addr}")

        if rtype == "databricks_default_namespace_setting" and ("update" in actions or "delete" in actions):
            warnings.append(
                "CHANGE the default catalog. Unqualified table names in notebooks, queries and jobs "
                "resolve to a different catalog.\n      " + addr
            )

        if rtype == "databricks_compliance_security_profile_workspace_setting" and "create" in actions:
            warnings.append(
                "ENABLE the compliance security profile. ONE-WAY: it cannot be turned off again, "
                "and it limits compute options.\n      " + addr
            )

        if rtype == "databricks_disable_legacy_access_setting" and ("create" in actions or "update" in actions):
            after = (rc["change"].get("after") or {}).get("disable_legacy_access") or [{}]
            if after[0].get("value") is True and actions == ["create"] and nothing_uses_legacy(args.preflight):
                notes.append(
                    "DISABLE legacy access (Hive metastore), on a workspace where it is not managed yet. "
                    "Preflight found nothing that still uses it (Hive metastore, DBFS mounts, legacy "
                    f"clusters), so it is not flagged. ONE-WAY after 30 days.\n      {addr}"
                )
            elif after[0].get("value") is True:
                warnings.append(
                    "DISABLE legacy access (Hive metastore). ONE-WAY: after 30 days the workspace "
                    f"is Unity Catalog only, permanently.\n      {addr}"
                )

    if releases:
        print("\nLeft unmanaged from now on (removed from Terraform's state on apply; the workspace")
        print("keeps its current values, nothing is deleted or reset):")
        for a in releases:
            print(f"  - RELEASE {a}")
        print()
    if notes:
        print("\nNot flagged, with the evidence:")
        for n in notes:
            print(f"  - {n}")
        print()
    if not warnings:
        return 0

    one = len(warnings) == 1
    print(f"\nNeeds approval: {len(warnings)} change{'' if one else 's'} that {'is' if one else 'are'} hard to undo or weaken{'s' if one else ''} security")
    print("(a person adds the label allow-risky-changes once they have reviewed them):")
    for w in warnings:
        print(f"  - {w}")
    print()
    return 2


if __name__ == "__main__":
    sys.exit(main())
