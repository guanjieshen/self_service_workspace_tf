"""Make, deploy and remove a Databricks App with its Lakebase database and SQL warehouse access.

In a notebook (serverless), as the person building the app:

    import sys; sys.path.append("/Workspace/.assistant/skills/build-a-databricks-app")
    from deploy_app import new_app, deploy, remove
    new_app("/Workspace/Users/me@example.com/apps/gtm-app-well-tracker")   # a new app: the starter, once
    deploy(prefix="gtm", name="well-tracker", folder=..., description=..., warehouse=..., leave_on=False, tags={...})
    remove(prefix="gtm", name="well-tracker")                               # the app, its database and its data

Safe to run again: what exists is updated, never made twice. The standards it applies: the name
<prefix>-app-<name> for the app and its database; the creator's default usage policy on both;
Lakebase at its smallest size, suspended after 5 idle minutes; both tagged with the workspace's tags
and APP, OWNER, CREATED_WITH, and the app with LEAVE_ON (false: it may be turned off when it isn't
needed); queries run as the signed-in person.
"""
import base64
import json
import os
import re
import shutil
import time
import urllib.parse

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

HERE = os.path.dirname(os.path.abspath(__file__))
SMALLEST = {"autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 0.5, "suspend_timeout_duration": "300s"}
_w = None


# ---- Calling Databricks ----

def _client():
    global _w
    _w = _w or WorkspaceClient()
    return _w


def _do(method, path, **kw):
    return _client().api_client.do(method, path, **kw)


def _get(path):
    """GET, or None when it does not exist."""
    try:
        return _do("GET", path)
    except NotFound:
        return None
    except Exception as e:   # some APIs answer a missing object with a plain message
        if "does not exist" in str(e) or "RESOURCE_DOES_NOT_EXIST" in str(e):
            return None
        raise


def _wait(what, check, minutes=15):
    """check() until it returns something; a timeout says that deploy() can simply run again."""
    end = time.time() + minutes * 60
    while time.time() < end:
        out = check()
        if out:
            return out
        time.sleep(10)
    raise TimeoutError(f"{what}: not ready after {minutes} minutes. Run deploy() again: it carries on.")


# ---- Workspace files (through the Workspace API: what a deployment reads) ----

def _api_path(path):
    path = path[len("/Workspace"):] if path.startswith("/Workspace/") else path
    return urllib.parse.quote(path, safe="/@")


def _read(path):
    out = _get(f"/api/2.0/workspace/export?path={_api_path(path)}&format=AUTO")
    return base64.b64decode(out["content"]).decode() if out and out.get("content") else None


def _write(path, text):
    """Write a file, then wait until it reads back: a deployment started right after a write through
    /Workspace (open()) can miss the file."""
    _do("POST", "/api/2.0/workspace/import", body={"path": urllib.parse.unquote(_api_path(path)), "format": "AUTO",
                                                    "overwrite": True, "content": base64.b64encode(text.encode()).decode()})
    _wait(f"{path} to be saved", lambda: _read(path) == text, 2)


# ---- Names and the starter ----

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
    """A new app: copy the starter (template/) into an empty folder. To change an app that exists,
    edit its folder and run deploy() again instead."""
    folder = folder.rstrip("/")
    if os.path.exists(os.path.join(folder, "package.json")):
        raise FileExistsError(f"{folder} already has an app: change its files and run deploy() again")
    if os.path.exists(folder) and os.listdir(folder):
        raise FileExistsError(f"{folder} is not empty: choose a new folder for a new app")
    shutil.copytree(os.path.join(HERE, "template"), folder, dirs_exist_ok=True)
    return sorted(os.path.relpath(os.path.join(d, f), folder) for d, _, fs in os.walk(folder) for f in fs)


# ---- The steps of deploy() ----

def _warehouse(wanted):
    whs = _do("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
    wh = next((x for x in whs if wanted in (x["id"], x["name"])), None)
    if not wh:
        raise ValueError(f"No SQL warehouse {wanted!r} you can use. Yours: {', '.join(x['name'] for x in whs) or 'none'}")
    return wh


def _tags(name, tags):
    """The workspace's tags, then the app's own: what it is, who it belongs to, how it was made."""
    return {**{k: str(v) for k, v in (tags or {}).items() if v not in (None, "")},
            "APP": name, "OWNER": _client().current_user.me().user_name, "CREATED_WITH": "genie-code"}


def _tag_app(name, tags):
    """The app's own tags (workspace entity tags), each set to its value: added, or replaced when it
    changed. Reads lag a few seconds behind writes, so an add that finds the tag still there waits and
    tries again, as does one that collides with a change still in progress. A tag the workspace refuses (for example a governed one) is a warning, not a failure."""
    base = f"/api/2.0/entity-tag-assignments/apps/{name}/tags"
    have = {a["tag_key"]: a.get("tag_value") for a in (_get(base) or {}).get("tag_assignments", [])}
    for key, value in tags.items():
        if have.get(key) == value:
            continue
        try:
            for attempt in range(8):
                try:
                    if key in have or attempt:
                        try:
                            _do("DELETE", f"{base}/{urllib.parse.quote(key)}")
                        except NotFound:
                            pass
                    _do("POST", "/api/2.0/entity-tag-assignments",
                        body={"entity_type": "apps", "entity_id": name, "tag_key": key, "tag_value": value})
                    break
                except Exception as e:   # the last write not visible yet, or one still in progress
                    if not re.search(r"already exists|[Cc]oncurrent|retry", str(e)) or attempt == 7:
                        raise
                    time.sleep(5)
        except Exception as e:
            print(f"Warning: could not tag the app {key}={value}: {e}")


def _ensure_database(name, description, tags):
    """The app's Lakebase project: made, brought back (removed in the last 7 days), or brought in
    line (tags, size, suspend). Returns (its endpoint, the app resource for its database)."""
    spec = {"display_name": f"{name}: {description}"[:256], "custom_tags": [{"key": k, "value": v} for k, v in tags.items()],
            "default_endpoint_settings": SMALLEST}
    found = _get(f"/api/2.0/postgres/projects/{name}")
    if found and found.get("delete_time"):   # its name is still taken for 7 days
        _do("POST", f"/api/2.0/postgres/projects/{name}/undelete", body={})
        print(f"Restored the database {name} (removed on {found['delete_time'][:10]}), with its data.")
    if not found:
        _do("POST", "/api/2.0/postgres/projects", query={"project_id": name}, body={"spec": {**spec, "pg_version": 17}})
        print(f"Creating the database {name}...")
    else:
        _do("PATCH", f"/api/2.0/postgres/projects/{name}", query={"update_mask": "spec.display_name,spec.custom_tags,spec.default_endpoint_settings"},
            body={"spec": spec})
    branch = _wait("the database", lambda: ((_get(f"/api/2.0/postgres/projects/{name}") or {}).get("status") or {}).get("default_branch"))
    endpoint = _wait("its endpoint", lambda: next(iter((_get(f"/api/2.0/postgres/{branch}/endpoints") or {}).get("endpoints", [])), None))["name"]
    dbs = (_get(f"/api/2.0/postgres/{branch}/databases") or {}).get("databases", [])
    database = next((d["name"] for d in dbs if (d.get("status") or {}).get("postgres_database") == "databricks_postgres"),
                    dbs[0]["name"] if dbs else None)
    if not database:
        raise RuntimeError(f"{branch} has no database yet: run deploy() again in a minute")
    return endpoint, {"name": "database", "postgres": {"branch": branch, "database": database, "permission": "CAN_CONNECT_AND_CREATE"}}


def _app_state(name):
    return ((_get(f"/api/2.0/apps/{name}") or {}).get("compute_status") or {}).get("state")


def _ensure_app(name, description, resources):
    """The app, made or updated, and running. No usage policy named: Databricks applies the creator's default."""
    spec = {"description": description, "resources": resources, "user_api_scopes": ["sql"]}
    try:
        if _get(f"/api/2.0/apps/{name}"):
            _do("PATCH", f"/api/2.0/apps/{name}", body=spec)
        else:
            _do("POST", "/api/2.0/apps", body={"name": name, **spec})
            print(f"Creating the app {name} (its compute takes a few minutes)...")
    except Exception as e:
        if "already exists" in str(e) or "PERMISSION_DENIED" in str(e):
            raise RuntimeError(f"The name {name} is taken by an app you can't change: choose another name") from e
        raise
    if _app_state(name) in ("STOPPED", "ERROR"):   # stopped by someone: start it, or nothing can be deployed
        _do("POST", f"/api/2.0/apps/{name}/start", body={})
        print(f"Starting the app {name}...")
    _wait("the app's compute", lambda: _app_state(name) == "ACTIVE", 20)
    return _do("GET", f"/api/2.0/apps/{name}")


def _write_app_yaml(folder, endpoint):
    yaml = ("# Written by deploy(): run it again rather than editing this.\ncommand: ['npm', 'run', 'start']\nenv:\n"
            "  - name: DATABRICKS_WAREHOUSE_ID\n    valueFrom: sql-warehouse\n")
    if endpoint:
        yaml += f"  - name: LAKEBASE_ENDPOINT\n    value: '{endpoint}'\n"
    _write(f"{folder}/app.yaml", yaml)
    _wait("the app's files", lambda: _read(f"{folder}/package.json"), 2)   # new_app() may have just run


def _yaml(value):
    """value as YAML (JSON is valid YAML: quoted strings, so names and tags never need escaping)."""
    return json.dumps(value)


def _write_bundle(folder, name, description, warehouse_id, tags, database, policy):
    """databricks.yml: the app (and its database) as a Databricks Asset Bundle, the same as deploy()
    made them, so the app can move into Git and CI/CD (the skill take-an-app-to-production) as it is."""
    lines = [
        "# The app as a Databricks Asset Bundle: everything deploy() made, in code, so it can move into Git and",
        "# CI/CD as it is (the skill take-an-app-to-production). Written by deploy(): run it again rather than",
        "# editing this. Once the app is in production, this file is its definition: change it through Git.",
        f"bundle:\n  name: {_yaml(name)}\n",
        "variables:\n  warehouse_id:\n    description: The SQL warehouse the app queries",
        f"    default: {_yaml(warehouse_id)}\n",
        "resources:",
    ]
    if database:
        lines += [
            "  postgres_projects:\n    database:",
            f"      project_id: {_yaml(name)}\n      display_name: {_yaml(f'{name}: {description}'[:256])}\n      pg_version: 17",
            f"      custom_tags: {_yaml([{'key': k, 'value': v} for k, v in tags.items()])}",
            f"      default_endpoint_settings: {_yaml(SMALLEST)}",
        ] + ([f"      budget_policy_id: {_yaml(policy)}"] if policy else [])
    lines += [
        "  apps:\n    app:",
        f"      name: {_yaml(name)}\n      description: {_yaml(description)}\n      source_code_path: .",
        "      user_api_scopes: [sql]\n      resources:",
        "        - name: sql-warehouse\n          sql_warehouse:\n            id: ${var.warehouse_id}\n            permission: CAN_USE",
    ]
    if database:
        db_id = database["postgres"]["database"].rsplit("/", 1)[1]
        lines += ["        - name: database\n          postgres:",
                  "            branch: ${resources.postgres_projects.database.name}/branches/production",
                  f"            database: ${{resources.postgres_projects.database.name}}/branches/production/databases/{db_id}",
                  "            permission: CAN_CONNECT_AND_CREATE"]
    lines += ["", "targets:\n  production:\n    mode: production\n    default: true",
              f"    workspace:\n      host: {_yaml(_client().config.host)}",
              "      root_path: /Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}"]
    _write(f"{folder}/databricks.yml", "\n".join(lines) + "\n")


def _start_deployment(name, folder):
    """Ask for a deployment; while another is in progress (starting a stopped app redeploys its last
    version, and the API does not always show that one), wait and ask again."""
    def ask():
        try:
            return _do("POST", f"/api/2.0/apps/{name}/deployments", body={"source_code_path": folder, "mode": "SNAPSHOT"})
        except Exception as e:
            if "deployment in progress" in str(e):
                return None
            raise
    return _wait("the deployment already running", ask, 20)


def _deployment_done(name, deployment_id):
    d = _do("GET", f"/api/2.0/apps/{name}/deployments/{deployment_id}")
    return d if (d.get("status") or {}).get("state") in ("SUCCEEDED", "FAILED", "CANCELLED") else None


# ---- What the skill calls ----

def deploy(prefix, name, folder, description, warehouse, leave_on, tags=None, lakebase=True):
    """Make or update the app (and its Lakebase database), then deploy folder. Returns what was made.
    leave_on: ask the person each time. True keeps it running; False lets it be turned off when unused."""
    full = app_name(prefix, name)
    if not isinstance(leave_on, bool):
        raise ValueError("leave_on: True (keep it running all the time) or False (it may be turned off when it "
                         "isn't needed). Ask the person which.")
    folder = folder.rstrip("/")
    if not os.path.exists(os.path.join(folder, "package.json")):
        raise FileNotFoundError(f"{folder} has no package.json: run new_app() first")
    if os.path.exists(os.path.join(folder, "package-lock.json")):
        os.remove(os.path.join(folder, "package-lock.json"))   # one made elsewhere points at another registry: the install fails
    description = (description or "").strip()[:200] or f"{full}: made with Genie Code"

    warehouse_id = _warehouse(warehouse)["id"]
    resources = [{"name": "sql-warehouse", "sql_warehouse": {"id": warehouse_id, "permission": "CAN_USE"}}]
    endpoint = database = None
    all_tags = _tags(full, tags)
    if lakebase:
        endpoint, database = _ensure_database(full, description, all_tags)
        resources.append(database)
    app = _ensure_app(full, description, resources)
    _tag_app(full, {**all_tags, "LEAVE_ON": str(leave_on).lower()})
    policy = app.get("effective_usage_policy_id") or app.get("effective_budget_policy_id")
    if not policy:
        print("Warning: no usage policy applies to you, so this app's costs are not charged to your business unit. "
              "Ask your platform admin for access to the workspace's usage policy.")
    elif endpoint:   # the database is charged to the app's policy
        _do("PATCH", f"/api/2.0/postgres/projects/{full}", query={"update_mask": "spec.budget_policy_id"},
            body={"spec": {"budget_policy_id": policy}})
    _write_app_yaml(folder, endpoint)
    _write_bundle(folder, full, description, warehouse_id, all_tags, database, policy)

    print("Deploying: Databricks installs the packages and builds the page, which takes a few minutes...")
    dep = _start_deployment(full, folder)
    done = _wait("the deployment", lambda: _deployment_done(full, dep["deployment_id"]), 20)
    app = _do("GET", f"/api/2.0/apps/{full}")
    out = {"app": full, "url": app.get("url"), "deployment": done["status"]["state"], "message": done["status"].get("message", ""),
           "logs": f"{app.get('url')}/logz", "leave_on": leave_on, "database": endpoint, "usage_policy": policy,
           "queries_run_as": "the signed-in person" if app.get("effective_user_api_scopes") else "the app"}
    print(json.dumps(out, indent=1))
    if done["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"The deployment {done['status']['state']}: {done['status'].get('message', '')}. The logs: {out['logs']}")
    return out


def remove(prefix, name, lakebase=True):
    """Delete the app and its Lakebase database (and with it the app's data). Safe to run again."""
    full = app_name(prefix, name)
    removed = []
    if _get(f"/api/2.0/apps/{full}"):
        _do("DELETE", f"/api/2.0/apps/{full}")
        removed.append(f"the app {full}")
    found = _get(f"/api/2.0/postgres/projects/{full}") if lakebase else None
    if found and not found.get("delete_time"):   # a deleted one still answers for 7 days
        _do("DELETE", f"/api/2.0/postgres/projects/{full}")
        removed.append(f"the database {full} and its data")
    print("Removed " + (" and ".join(removed) if removed else f"nothing: {full} does not exist (or was removed already)"))
    return removed
