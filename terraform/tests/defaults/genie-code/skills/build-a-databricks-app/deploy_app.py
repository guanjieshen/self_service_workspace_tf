"""Make, deploy and remove a Databricks App with its Lakebase database and SQL warehouse access.

In a notebook (serverless), as the person building the app:

    import sys; sys.path.append("/Workspace/.assistant/skills/build-a-databricks-app")
    from deploy_app import new_app, deploy, remove
    new_app("/Workspace/Users/me@example.com/apps/gtm-app-well-tracker")   # the starter, once
    deploy(prefix="gtm", name="well-tracker", folder=..., description=..., warehouse=..., tags={...})
    remove(prefix="gtm", name="well-tracker")                               # the app, its database and its data

Safe to run again: what exists is updated, never made twice. The standards it applies: the name
<prefix>-app-<name> for the app and its database; the creator's default usage policy on both;
Lakebase at its smallest size, suspended after 5 idle minutes, tagged with the workspace's tags
and APP, OWNER, CREATED_WITH and EXPIRES (30 days); queries run as the signed-in person.
"""
import base64
import datetime
import json
import os
import re
import shutil
import time

from databricks.sdk import WorkspaceClient

HERE = os.path.dirname(os.path.abspath(__file__))
_w = None


def _client():
    global _w
    _w = _w or WorkspaceClient()
    return _w


def _do(method, path, **kw):
    return _client().api_client.do(method, path, **kw)


def _get(path):
    try:
        return _do("GET", path)
    except Exception as e:
        if any(s in str(e) for s in ("not found", "does not exist", "RESOURCE_DOES_NOT_EXIST", "Not Found")):
            return None
        raise


def _wait(what, check, minutes=15):
    end = time.time() + minutes * 60
    while time.time() < end:
        out = check()
        if out:
            return out
        time.sleep(10)
    raise TimeoutError(f"{what}: not ready after {minutes} minutes. Run deploy() again: it carries on.")


def _api_path(path):
    return path[len("/Workspace"):] if path.startswith("/Workspace/") else path


def _read(path):
    """A workspace file's text, through the Workspace API (what a deployment reads), or None."""
    out = _get(f"/api/2.0/workspace/export?path={_api_path(path)}&format=AUTO")
    return base64.b64decode(out["content"]).decode() if out and out.get("content") else None


def _write(path, text):
    """Write a workspace file through the Workspace API, then wait until it reads back: a deployment
    started right after a write through /Workspace (open()) can miss the file."""
    _do("POST", "/api/2.0/workspace/import", body={"path": _api_path(path), "format": "AUTO", "overwrite": True,
                                                    "content": base64.b64encode(text.encode()).decode()})
    _wait(f"{path} to be saved", lambda: _read(path) == text, 2)


def app_name(prefix, name):
    """The naming standard: <prefix>-app-<name>, at most 30 characters."""
    prefix, name = (prefix or "").strip().lower(), (name or "").strip().lower()
    name = name[len(f"{prefix}-app-"):] if name.startswith(f"{prefix}-app-") else name
    full = f"{prefix}-app-{name}"
    if not re.fullmatch(r"[a-z][a-z0-9]{1,9}", prefix):
        raise ValueError(f"prefix: the workspace's prefix, lower case (for example gtm), not {prefix!r}")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(full) > 30:
        raise ValueError(f"name: lowercase letters, digits and dashes, at most {30 - len(prefix) - 5} characters after "
                         f"{prefix}-app- (the whole name is at most 30), not {name!r}")
    return full


def new_app(folder):
    """Copy the starter (template/) into folder: a working app to change, not one to write from scratch."""
    folder = folder.rstrip("/")
    if os.path.exists(folder) and os.listdir(folder):
        raise FileExistsError(f"{folder} is not empty: choose a new folder, or change the app that is there")
    shutil.copytree(os.path.join(HERE, "template"), folder, dirs_exist_ok=True)
    return sorted(os.path.relpath(os.path.join(d, f), folder) for d, _, fs in os.walk(folder) for f in fs)


def deploy(prefix, name, folder, description, warehouse, tags=None, lakebase=True):
    """Make or update the app (and its Lakebase database), then deploy folder. Returns what was made."""
    full = app_name(prefix, name)
    folder = folder.rstrip("/")
    if not os.path.exists(os.path.join(folder, "package.json")):
        raise FileNotFoundError(f"{folder} has no package.json: run new_app() first")
    if os.path.exists(os.path.join(folder, "package-lock.json")):
        os.remove(os.path.join(folder, "package-lock.json"))   # one made elsewhere points at another registry: the install fails
    description = (description or "").strip()[:200] or f"{full}: made with Genie Code"
    me = _client().current_user.me().user_name

    whs = _do("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
    wh = next((x for x in whs if warehouse in (x["id"], x["name"])), None)
    if not wh:
        raise ValueError(f"No SQL warehouse {warehouse!r} you can use. Yours: {', '.join(x['name'] for x in whs) or 'none'}")
    resources = [{"name": "sql-warehouse", "sql_warehouse": {"id": wh["id"], "permission": "CAN_USE"}}]

    endpoint = None
    all_tags = {**{k: str(v) for k, v in (tags or {}).items() if v not in (None, "")},
                "APP": full, "OWNER": me, "CREATED_WITH": "genie-code",
                "EXPIRES": (datetime.date.today() + datetime.timedelta(days=30)).isoformat()}
    if lakebase:
        found = _get(f"/api/2.0/postgres/projects/{full}")
        if found and found.get("delete_time"):   # removed in the last 7 days: its name is still taken, so bring it back
            _do("POST", f"/api/2.0/postgres/projects/{full}/undelete", body={})
            print(f"Restored the Lakebase database {full} (removed on {found['delete_time'][:10]}), with its data.")
        elif not found:
            # The smallest size, suspended after 5 idle minutes, tagged for chargeback and cleanup.
            _do("POST", "/api/2.0/postgres/projects", query={"project_id": full},
                body={"spec": {"display_name": f"{full}: {description}"[:256], "pg_version": 17,
                               "custom_tags": [{"key": k, "value": v} for k, v in all_tags.items()],
                               "default_endpoint_settings": {"autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 0.5,
                                                             "suspend_timeout_duration": "300s"}}})
            print(f"Creating the Lakebase database {full}...")
        branch = _wait("the Lakebase project", lambda: ((_get(f"/api/2.0/postgres/projects/{full}") or {}).get("status") or {}).get("default_branch"))
        ep = _wait("its endpoint", lambda: next(iter((_get(f"/api/2.0/postgres/{branch}/endpoints") or {}).get("endpoints", [])), None))
        endpoint = ep["name"]
        dbs = (_get(f"/api/2.0/postgres/{branch}/databases") or {}).get("databases", [])
        database = next((d["name"] for d in dbs if (d.get("status") or {}).get("postgres_database") == "databricks_postgres"),
                        dbs[0]["name"] if dbs else None)
        if not database:
            raise RuntimeError(f"{branch} has no database yet: run deploy() again in a minute")
        resources.append({"name": "database", "postgres": {"branch": branch, "database": database, "permission": "CAN_CONNECT_AND_CREATE"}})

    # The app. No usage policy named: Databricks applies the creator's default one (it carries the tags).
    spec = {"description": description, "resources": resources, "user_api_scopes": ["sql"]}
    existing = _get(f"/api/2.0/apps/{full}")
    if existing:
        _do("PATCH", f"/api/2.0/apps/{full}", body=spec)
    else:
        _do("POST", "/api/2.0/apps", body={"name": full, **spec})
        print(f"Creating the app {full} (its compute takes a few minutes)...")
    app = _wait("the app's compute", lambda: (lambda a: a if (a.get("compute_status") or {}).get("state") == "ACTIVE" else None)(_do("GET", f"/api/2.0/apps/{full}")), 20)
    policy = app.get("effective_usage_policy_id") or app.get("effective_budget_policy_id")
    if endpoint and policy:   # the database is charged to the app's policy
        _do("PATCH", f"/api/2.0/postgres/projects/{full}", query={"update_mask": "spec.budget_policy_id"},
            body={"spec": {"budget_policy_id": policy}})

    # app.yaml: how the server finds the warehouse and the database; always matches the resources.
    yaml = ("# Written by deploy(): run it again rather than editing this.\ncommand: ['npm', 'run', 'start']\nenv:\n"
            "  - name: DATABRICKS_WAREHOUSE_ID\n    valueFrom: sql-warehouse\n")
    if endpoint:
        yaml += f"  - name: LAKEBASE_ENDPOINT\n    value: '{endpoint}'\n"
    _write(f"{folder}/app.yaml", yaml)
    # The deployment reads the folder through the Workspace API: wait until it sees the app (new_app() just ran?).
    _wait("the app's files", lambda: _read(f"{folder}/package.json"), 2)

    # Deploy: Databricks runs npm install, npm run build, then npm run start.
    dep = _do("POST", f"/api/2.0/apps/{full}/deployments", body={"source_code_path": folder, "mode": "SNAPSHOT"})
    print("Deploying (npm install and the build take a few minutes)...")
    done = _wait("the deployment", lambda: (lambda d: d if (d.get("status") or {}).get("state") in ("SUCCEEDED", "FAILED", "CANCELLED") else None)(
        _do("GET", f"/api/2.0/apps/{full}/deployments/{dep['deployment_id']}")), 20)
    app = _do("GET", f"/api/2.0/apps/{full}")
    out = {"app": full, "url": app.get("url"), "deployment": done["status"]["state"], "message": done["status"].get("message", ""),
           "logs": f"{app.get('url')}/logz", "lakebase": endpoint, "usage_policy": policy,
           "queries_run_as": "the signed-in person" if app.get("effective_user_api_scopes") else "the app"}
    print(json.dumps(out, indent=1))
    if done["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"The deployment {done['status']['state']}: {done['status'].get('message', '')}. Read the logs: {out['logs']}")
    return out


def remove(prefix, name, lakebase=True):
    """Delete the app and its Lakebase database (and with it the app's data)."""
    full = app_name(prefix, name)
    removed = []
    if _get(f"/api/2.0/apps/{full}"):
        _do("DELETE", f"/api/2.0/apps/{full}")
        removed.append(f"the app {full}")
    if lakebase and _get(f"/api/2.0/postgres/projects/{full}"):
        _do("DELETE", f"/api/2.0/postgres/projects/{full}")
        removed.append(f"the Lakebase database {full} and its data")
    print("Removed " + (" and ".join(removed) if removed else f"nothing: {full} does not exist"))
    return removed
