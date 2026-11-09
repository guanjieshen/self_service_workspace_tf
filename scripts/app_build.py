#!/usr/bin/env python3
"""Build what the self-service bundles deploy, from config/self-service/ and the workspaces it serves.

  python3 scripts/app_build.py hub --outputs <outputs.json>
  python3 scripts/app_build.py <workspace> --outputs <outputs.json>

The app's settings are config/self-service/app.yaml and hub.yaml. The workspaces it serves are
the workspace files in config/workspaces/ without self_service: false. What the app needs to
know about each of them (prefix, ID, host, catalog, usage policy) is that workspace's Terraform
output self_service (terraform/self_service.tf), never repeated here: outputs.json holds them,
{workspace: output}, and scripts/app_deploy.py writes it from the state.

Writes, not in Git:

  bundle/hub/build/            the hub: each app's code with its config.json, and target.yml
  bundle/jobs/build/<ws>/      a served workspace: the job notebooks (with their settings written
                               in: a run can pass any parameter, so what it must not change cannot
                               be one), and target.yml

Needs PyYAML. Changes nothing in a workspace.
"""
import argparse
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "apps/self-service"
NOTEBOOKS = ROOT / "bundle/jobs/notebooks"
CONFIG = ROOT / "config/self-service"
WORKSPACES = ROOT / "config/workspaces"
# Not part of the app's code: its tests, notes, database scripts and local files.
SKIP = ("__pycache__", ".pyc", ".gitignore", "config.json", "tests", "AGENTS.md", "db")
KINDS = ("personal_schema", "project_schema", "team_schema", "temporary_schema", "temporary_extension", "temporary_conversion", "folder")
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+"


def _yaml(path):
    import yaml   # here, so the notebook tests need only the standard library
    return yaml.safe_load(path.read_text()) or {}


def load(config_dir=None, workspaces_dir=None):
    """The app's settings: {app, jobs, hub, database, app_ids, adopt, spokes}. spokes: the served
    workspaces' names, in order."""
    config_dir, workspaces_dir = config_dir or CONFIG, workspaces_dir or WORKSPACES
    app_file, hub_file = _yaml(config_dir / "app.yaml"), _yaml(config_dir / "hub.yaml")
    spokes = sorted(f.stem for f in workspaces_dir.glob("*.yaml")
                    if not f.stem.startswith("_") and _yaml(f).get("self_service", True) is not False)
    s = {"app": app_file.get("self_service_app") or {}, "jobs": app_file.get("jobs") or {},
         "hub": hub_file.get("hub") or {}, "database": hub_file.get("database") or {},
         "app_ids": hub_file.get("app_ids") or {}, "adopt": hub_file.get("adopt") or {}, "spokes": spokes}
    check(s)
    return s


def ai_model(app):
    """The model every AI feature uses (app.yaml ai_model). An app.yaml from 1.0.x names it as the
    summary's (ai_summary.model): still read, so an upgrade keeps it."""
    return str(app.get("ai_model") or (app.get("ai_summary") or {}).get("model") or "")


# A temporary schema's rights when app.yaml names none: use it fully, never share it.
TEMPORARY_PRIVILEGES = ['USE_SCHEMA', 'SELECT', 'MODIFY', 'CREATE_TABLE', 'CREATE_VOLUME', 'READ_VOLUME', 'WRITE_VOLUME', 'CREATE_FUNCTION', 'EXECUTE', 'CREATE_MATERIALIZED_VIEW']


def temporary_privileges(jobs):
    """What a temporary schema's requester is granted (app.yaml jobs.temporary_schema.privileges)."""
    return list((jobs.get("temporary_schema") or {}).get("privileges") or TEMPORARY_PRIVILEGES)


def check(s):
    """Settings that would fail later (in a deploy, or in the app), refused now, naming the setting."""
    app, hub, db, jobs = s["app"], s["hub"], s["database"], s["jobs"]
    problems = []
    need = lambda ok, message: ok or problems.append(message)
    need(re.fullmatch(r"https://[^\s/]+/?", hub.get("host") or ""), "hub.yaml hub.host: the hub's https:// per-workspace URL.")
    need(re.fullmatch(r"\w+", hub.get("name") or ""), "hub.yaml hub.name: the hub's name (letters, digits and _).")
    for key, name in (("name", app.get("name")), ("approvals.name", (app.get("approvals") or {}).get("name"))):
        need(re.fullmatch(r"[a-z0-9-]{2,30}", name or ""), f"app.yaml self_service_app.{key}: 2 to 30 lowercase letters, digits and dashes.")
    need(str(app.get("ai_check")) in ("on", "off"), "app.yaml self_service_app.ai_check: on or off.")
    days = (jobs.get("temporary_schema") or {}).get("days", 30)
    need(isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= 365, "app.yaml jobs.temporary_schema.days: a whole number of days, 1 to 365.")
    limit = (jobs.get("temporary_schema") or {}).get("limit", 1)
    need(isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 10, "app.yaml jobs.temporary_schema.limit: how many temporary schemas a person may have, 1 to 10.")
    rights = temporary_privileges(jobs)
    need(all(isinstance(p, str) and re.fullmatch(r"[A-Z_]+", p) for p in rights) and not {"MANAGE", "ALL_PRIVILEGES"} & set(rights),
         "app.yaml jobs.temporary_schema.privileges: privileges such as SELECT or CREATE_TABLE; never MANAGE or ALL_PRIVILEGES, which let the requester share it.")
    need(re.fullmatch(r"[\w.-]{0,100}", ai_model(app)), "app.yaml self_service_app.ai_model: a model's name (for example system.ai.claude-sonnet-5-5), or null.")
    need(set(app.get("human_approval") or []) <= set(KINDS), f"app.yaml self_service_app.human_approval lists kinds of request: {', '.join(KINDS)}.")
    need(all(u is None or re.match(r"https?://", u) for u in (app.get("faq") or {}).values()),
         "app.yaml self_service_app.faq: each link starts with https://, or is null for no link.")
    need(len((app.get("onboarding") or {}).get("prompt") or "") <= 1000, "app.yaml self_service_app.onboarding.prompt: keep it under 1,000 characters.")
    if (app.get("bu_lookup") or {}).get("function"):
        need(re.fullmatch(r"\w+\.\w+\.\w+", app["bu_lookup"]["function"]), "app.yaml self_service_app.bu_lookup.function: catalog.schema.function (letters, digits and _).")
        need(re.fullmatch(r"[0-9a-f]+", str(hub.get("warehouse_id") or "")), "hub.yaml hub.warehouse_id: the SQL warehouse the business unit lookup runs on.")
    # The readers' emails go on the migrations' command line: plain addresses only.
    need(all(re.fullmatch(EMAIL, r) for r in db.get("readers") or []), "hub.yaml database.readers: plain email addresses.")
    need(all(v is None or re.fullmatch(r"[0-9a-f-]{36}", str(v)) for v in s["app_ids"].values()), "hub.yaml app_ids: the apps' service principals' application IDs, or null.")
    need(s["adopt"].get("database") is None or re.fullmatch(r"projects/[a-z0-9-]+", str(s["adopt"]["database"])),
         "hub.yaml adopt.database: the project's resource name, projects/<project ID> (for example projects/cd-self-service).")
    if jobs.get("require_request_record"):
        need(re.fullmatch(r"[a-z0-9_]+", (app.get("database") or {}).get("catalog") or ""),
             "app.yaml jobs.require_request_record needs the app's records in Unity Catalog: set self_service_app.database.catalog.")
    need(re.fullmatch(r"/Workspace/[^\s]+", jobs.get("admin_path") or ""), "app.yaml jobs.admin_path: a folder under /Workspace.")
    if problems:
        raise SystemExit("config/self-service:\n" + "\n".join(f"  - {m}" for m in problems))


def served(s, outputs):
    """The served workspaces as the app knows them, from their Terraform outputs: [{name, bu, host,
    id, catalog, usage_policy_id}]. A workspace without an output (never applied) stops the build."""
    out = []
    for name in s["spokes"]:
        o = outputs.get(name)
        if not o or not o.get("host"):
            raise SystemExit(f"No Terraform output for {name}: apply its baseline first (it has no self_service: false).")
        if not o.get("catalog"):
            raise SystemExit(f"{name} has no catalog (catalog: null), so its schema job has nowhere to create schemas: set self_service: false, or give it a catalog.")
        out.append({"name": name, "bu": o["prefix"].upper(), "host": o["host"].rstrip("/"), "id": str(o.get("id") or ""),
                    "catalog": o["catalog"], "usage_policy_id": o.get("usage_policy_id"),
                    "platform_admins": list(o.get("platform_admins") or [])})
    return out


def app_config(s, spokes, mode=None):
    """Each app's config.json: what the app reads (main.py, portal.py)."""
    app, hub, db = s["app"], s["hub"], s["database"]
    host = hub["host"].rstrip("/")
    lookup = app.get("bu_lookup") or {}
    config = {
        "title": app["title"],
        "hub_host": host,   # where the jobs run: an admin's link to a request's run opens there
        "folder_root": s["jobs"].get("folder_root") or "/Workspace",
        "temporary_days": int((s["jobs"].get("temporary_schema") or {}).get("days") or 30),   # what the temporary schema form says
        "temporary_limit": int((s["jobs"].get("temporary_schema") or {}).get("limit") or 1),   # the default: Settings > Schemas changes it   # where folders go (made by hand for now)
        "faq": dict(app.get("faq") or {}),
        "ai_check": str(app.get("ai_check") or "off"),
        "human_approval": list(app.get("human_approval") or []),
        "ai": {"model": ai_model(app)},
        "bu_lookup": {"function": lookup["function"], "warehouse_id": hub["warehouse_id"], "host": host}
                     if lookup.get("function") else None,
        "links": dict(app.get("links") or {}),   # {host}, {workspace_id}, {catalog}: the person's workspace's, filled in by the app
        "onboarding": {"prompt": (app.get("onboarding") or {}).get("prompt") or ""},
        # The workspaces it serves: the business unit is each one's prefix.
        "workspaces": [{"name": w["name"], "bu": w["bu"], "host": w["host"], "id": w["id"], "catalog": w["catalog"]} for w in spokes],
        "database": {"host": db.get("host"), "name": "self_service",
                     "endpoint": f"projects/{app['database']['project_id']}/branches/production/endpoints/primary"},
    }
    return {**config, "mode": mode} if mode else config


def render(text, values):
    """A job notebook's text with its settings written in: ${jsonencode(x)}, and the shared
    request record check (off unless requests_catalog is set)."""
    values = {"requests_catalog": "", "workspace_name": "", "human_approval": [], **values}
    text = text.replace("${request_record_check}", (NOTEBOOKS / "request_record_check.py").read_text())
    return re.sub(r"\$\{jsonencode\((\w+)\)\}", lambda m: json.dumps(values[m.group(1)]), text)


def notebook(name, values):
    return render((NOTEBOOKS / f"{name}.py").read_text(), values)


def hub_target(s, database=True):
    """The hub bundle's target: where, the variables, what each app may use and who may open it.
    database False: the apps without their database resource, for a first install's first pass
    (an app cannot name a database that does not exist yet; app_deploy.py creates it after the project)."""
    app, hub = s["app"], s["hub"]
    db = app["database"]
    can_use = lambda group: [{"level": "CAN_USE", "group_name": group}] if group and group != "admins" else []
    branch = "${resources.postgres_projects.database.name}/branches/production"
    uses = [{"name": "database", "postgres": {"branch": branch, "database": f"{branch}/databases/self-service",
                                              "permission": "CAN_CONNECT_AND_CREATE"}}] if database else []
    warehouse = [{"name": "warehouse", "sql_warehouse": {"id": hub["warehouse_id"], "permission": "CAN_USE"}}] \
        if (app.get("bu_lookup") or {}).get("function") else []   # the business unit lookup runs on it, as the app
    return {"targets": {"hub": {
        "mode": "production",
        "workspace": {"host": hub["host"], "root_path": f"{s['jobs']['admin_path']}/bundle/hub"},
        "variables": {
            "self_service_name": app["name"],
            "approvals_name": app["approvals"]["name"],
            "database_project": db["project_id"],
            "database_display_name": f"{app['title']}: requests",
            "database_min_cu": db["min_cu"],
            "database_max_cu": db["max_cu"],
            "database_suspend_after": db["suspend_after"],
        },
        "resources": {"apps": {
            "self_service": {"resources": uses + warehouse, "permissions": can_use(hub.get("users_group"))},
            "approvals": {"resources": uses, "permissions": can_use(hub.get("approvals_group"))},
        }},
    }}}


def jobs_target(s, w, app_ids):
    """A served workspace's target in the jobs bundle: its schema job, deployed to the hub (Unity
    Catalog is the metastore's, and its catalog is bound to the hub too: terraform/self_service.tf),
    so the apps never call another workspace. Each business unit has its own state path in the hub,
    and its job says which workspace it serves (cd_workspace). Only workspace admins and the two
    apps (app_ids: their service principals' application IDs) may run it."""
    jobs = s["jobs"]
    runners = [{"level": "CAN_MANAGE_RUN", "service_principal_name": i} for i in app_ids]
    policy = {"usage_policy_id": w["usage_policy_id"]} if w.get("usage_policy_id") else {}
    return {"targets": {w["name"]: {
        "mode": "production",
        "workspace": {"host": s["hub"]["host"].rstrip("/"), "root_path": f"{jobs['admin_path']}/bundle/jobs/{w['name']}"},
        "variables": {"business_unit": w["bu"]},
        "resources": {"jobs": {
            "personal_schema": {"tags": {"cd_catalog": w["catalog"], "cd_prefix": jobs["personal_schema"]["prefix"],
                                         "cd_workspace": w["name"]},
                                "permissions": runners, **policy},
        }},
    }}}


def build_hub(s, spokes, database_host=None, database=True, root=None):
    """bundle/hub/build/: each app's code and config.json, the daily cleanup's notebook (with
    every served workspace's catalog), and target.yml. database_host: the database's endpoint, which
    app_deploy.py looks up (it is never stored)."""
    if database_host:
        s = {**s, "database": {**s["database"], "host": database_host}}
    out = (root or ROOT) / "bundle/hub/build"
    shutil.rmtree(out, ignore_errors=True)
    for app_dir, mode in (("self-service", None), ("approvals", "approvals")):
        shutil.copytree(APP, out / app_dir, ignore=lambda d, names: [n for n in names if any(n == k or n.endswith(k) for k in SKIP)])
        (out / app_dir / "config.json").write_text(json.dumps(app_config(s, spokes, mode), indent=1))
    (out / "temporary_cleanup.py").write_text(notebook("temporary_cleanup", {
        "prefix": s["jobs"]["personal_schema"]["prefix"], "allowed_catalogs": sorted({w["catalog"] for w in spokes}),
        "temporary_days": int((s["jobs"].get("temporary_schema") or {}).get("days") or 30),
        "temporary_privileges": temporary_privileges(s["jobs"])}))
    # JSON is YAML: the bundle reads it as an included file.
    (out / "target.yml").write_text(json.dumps(hub_target(s, database=database), indent=1))
    return out


def build_jobs(s, w, app_ids, root=None):
    """bundle/jobs/build/<workspace>/: the schema job's notebook, with its settings, and target.yml.
    (The folder job, bundle/jobs/notebooks/team_folder.py, is not deployed for now: a folder is
    workspace specific, and the hub does not call other workspaces.)"""
    jobs, app = s["jobs"], s["app"]
    out = (root or ROOT) / "bundle/jobs/build" / w["name"]
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    record = {"requests_catalog": app["database"].get("catalog") or "", "workspace_name": w["name"],
              "human_approval": list(app.get("human_approval") or [])} if jobs.get("require_request_record") else {}
    (out / "personal_schema.py").write_text(notebook("personal_schema", {
        "prefix": jobs["personal_schema"]["prefix"], "privileges": jobs["personal_schema"]["privileges"],
        "temporary_days": int((jobs.get("temporary_schema") or {}).get("days") or 30),
        "temporary_privileges": temporary_privileges(jobs),
        "owner": jobs.get("catalog_owner") or "", "allowed_catalogs": [w["catalog"]], **record}))
    (out / "target.yml").write_text(json.dumps(jobs_target(s, w, app_ids), indent=1))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("target", help="hub, or a served workspace's name")
    p.add_argument("--outputs", required=True, help="JSON {workspace: its Terraform output self_service}")
    a = p.parse_args(argv)
    s = load()
    spokes = served(s, json.loads(pathlib.Path(a.outputs).read_text()))
    if a.target == "hub":
        print(build_hub(s, spokes).relative_to(ROOT))
        return
    w = next((w for w in spokes if w["name"] == a.target), None)
    if w is None:
        raise SystemExit(f"{a.target} is not a workspace the app serves: {', '.join(s['spokes']) or 'none'}.")
    print(build_jobs(s, w, [i for i in s["app_ids"].values() if i]).relative_to(ROOT))


if __name__ == "__main__":
    sys.exit(main())
