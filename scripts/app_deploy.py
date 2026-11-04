#!/usr/bin/env python3
"""Deploy the self-service app: the hub (both apps and their database), then its jobs in every
workspace it serves.

  python3 scripts/app_deploy.py               deploy (GitHub Actions runs this on merge)
  python3 scripts/app_deploy.py --plan        show what a deploy would change; change nothing
  python3 scripts/app_deploy.py --only <ws>   the hub, and only that served workspace's jobs

Signed in with the Databricks CLI (DATABRICKS_AUTH_TYPE and its settings); the workspace of each
step comes from the configuration. The app and its jobs are Databricks Asset Bundles
(bundle/hub/, bundle/jobs/), never Terraform; what they need on Terraform's objects (catalog
grants, workspace assignment, the usage policy) Terraform grants (terraform/self_service.tf).

1. Read each served workspace's Terraform output self_service (scripts/tf.sh <ws> output).
2. The hub (config/self-service/hub.yaml):
   a. bind what existed before the bundle (adopt:), once;
   b. on a first install, deploy without the apps' database resource (an app cannot name a
      database that does not exist yet), then make the database;
   c. the database and its readers' roles if missing, then the migrations and grants, as the
      deploying identity: it must own the database or be a Lakebase superuser there (a first
      install makes it the owner; run every deploy as the same one);
   d. deploy the bundle, then each app's new code, so new code never meets an old database.
3. Each served workspace: its two jobs, which only the hub's two apps may run (app_ids in
   hub.yaml, the ones Terraform assigned to the workspace). A first install has none yet: the
   deploy prints them; set them in a pull request, whose deploy then grants them.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import app_build  # noqa: E402

HUB, JOBS = ROOT / "bundle/hub", ROOT / "bundle/jobs"


def env(host):
    return {**os.environ, "DATABRICKS_HOST": host}


NOT_FOUND = re.compile(r"not.?found|does not exist|RESOURCE_DOES_NOT_EXIST|404", re.I)


def cli(host, *args, missing_ok=False):
    """The Databricks CLI's JSON output in a workspace. missing_ok: None when what was asked for
    does not exist; any other failure (sign-in, network, permission) stops the deploy, so a
    passing outage is never read as "not there" (which would create it again). Run outside the
    bundles' folders, where the CLI would take a bundle's target instead."""
    r = subprocess.run(["databricks", *args, "-o", "json"], cwd=tempfile.gettempdir(), env=env(host), capture_output=True, text=True)
    if r.returncode:
        if missing_ok and NOT_FOUND.search(r.stderr):
            return None
        raise SystemExit(f"databricks {' '.join(args)} failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def run(host, cwd, *args):
    """A command whose output people read (the plan, the deploy)."""
    print("$", " ".join(str(a) for a in args), flush=True)
    subprocess.run(args, cwd=cwd, env=env(host), check=True)


def outputs(names):
    """Each served workspace's Terraform output self_service, read from its state."""
    out = {}
    for name in names:
        r = subprocess.run([str(ROOT / "scripts/tf.sh"), name, "output", "-json", "self_service"],
                           cwd=ROOT, capture_output=True, text=True)
        text = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else ""
        if r.returncode or not text:
            raise SystemExit(f"No Terraform output self_service for {name}: apply its baseline first.\n{r.stderr.strip()}")
        out[name] = json.loads(text)
    return out


def bind_adopted(host, adopt, plan):
    """Bind each hub resource listed under adopt: that the bundle does not manage yet."""
    summary = subprocess.run(["databricks", "bundle", "summary", "-t", "hub", "-o", "json"], cwd=HUB, env=env(host),
                             capture_output=True, text=True, check=True)
    resources = (json.loads(summary.stdout).get("resources") or {})
    managed = {key for kind in resources.values() for key, r in kind.items() if r.get("id")}
    for key, existing in (adopt or {}).items():
        if key in managed:
            continue
        if plan:
            print(f"would bind {key} to the existing {existing}")
            continue
        run(host, HUB, "databricks", "bundle", "deployment", "bind", key, str(existing), "-t", "hub", "--auto-approve")


def ensure_database(host, branch, owner, readers):
    """The database self_service, owned by the deploying identity, and a role for each reader."""
    roles = cli(host, "postgres", "list-roles", branch)
    roles = roles if isinstance(roles, list) else roles.get("roles", [])
    by_name = {(r.get("status") or {}).get("postgres_role"): r["name"] for r in roles}
    if cli(host, "postgres", "get-database", f"{branch}/databases/self-service", missing_ok=True) is None:
        if owner not in by_name:
            raise SystemExit(f"No Lakebase role for {owner} on {branch}: the deploying identity must have one.")
        cli(host, "postgres", "create-database", branch, "--database-id", "self-service",
            "--json", json.dumps({"spec": {"postgres_database": "self_service", "role": by_name[owner]}}))
        print("created the database self_service")
    for reader in readers:
        if reader not in by_name:
            cli(host, "postgres", "create-role", branch, "--json", json.dumps(
                {"spec": {"postgres_role": reader, "identity_type": "USER", "auth_method": "LAKEBASE_OAUTH_V1"}}))
            print(f"created a read-only role for {reader}")


def project_exists(host, project):
    """Whether the Lakebase project exists. A deleted one is kept for a while (it can be
    undeleted) and still answers: it stops the deploy, saying how to clear it."""
    p = cli(host, "postgres", "get-project", f"projects/{project}", missing_ok=True)
    if p is None:
        return False
    if p.get("delete_time"):
        raise SystemExit(f"The Lakebase project {project} was deleted ({p['delete_time']}) and is kept until {p.get('purge_time')}: "
                         f"undelete it (databricks postgres undelete-project projects/{project}), purge it "
                         f"(databricks postgres delete-project projects/{project} --purge), or name another project_id.")
    return True


def deploy_hub(s, spokes, plan):
    """The hub; returns the apps' service principals' application IDs."""
    host, app = s["hub"]["host"], s["app"]
    app_build.build_hub(s, spokes)
    bind_adopted(host, s["adopt"], plan)
    if plan:
        run(host, HUB, "databricks", "bundle", "plan", "-t", "hub")
        return [i for i in s["app_ids"].values() if i]
    project = app["database"]["project_id"]
    branch = f"projects/{project}/branches/production"
    owner = cli(host, "current-user", "me")["userName"]
    readers = list(s["database"].get("readers") or [])
    if not project_exists(host, project):
        app_build.build_hub(s, spokes, database=False)
        run(host, HUB, "databricks", "bundle", "deploy", "-t", "hub", "--auto-approve")
    ensure_database(host, branch, owner, readers)
    # The endpoint, looked up every time (never stored): a new database gets a new one.
    db_host = cli(host, "postgres", "get-endpoint", f"{branch}/endpoints/primary")["status"]["hosts"]["host"]
    app_build.build_hub(s, spokes, database_host=db_host)
    run(host, HUB, "databricks", "bundle", "deploy", "-t", "hub", "--auto-approve")

    ids = {key: cli(host, "apps", "get", name)["service_principal_client_id"]
           for key, name in (("self_service", app["name"]), ("approvals", app["approvals"]["name"]))}
    run(host, ROOT, sys.executable, str(ROOT / "apps/self-service/db/migrate.py"),
        "--host", db_host, "--database", "self_service", "--user", owner, "--endpoint", f"{branch}/endpoints/primary",
        "--grant", f"self_service={ids['self_service']}", "--grant", f"approvals={ids['approvals']}",
        "--grant", f"readers={','.join(readers)}")
    for key in ("self_service", "approvals"):
        run(host, HUB, "databricks", "bundle", "run", key, "-t", "hub")
    stored = {k: v for k, v in s["app_ids"].items() if v}
    if stored and stored != ids:
        raise SystemExit(f"config/self-service/hub.yaml app_ids {stored} are not the apps' service principals {ids}: fix app_ids.")
    if not stored:
        print(f"set app_ids in config/self-service/hub.yaml to {ids}, so the served workspaces grant the apps (terraform/self_service.tf)")
    return list(ids.values())


def deploy_jobs(s, w, app_ids, plan):
    """A served workspace's schema job, deployed to the hub (app_build.jobs_target)."""
    app_build.build_jobs(s, w, app_ids)
    host = s["hub"]["host"]
    if plan:
        run(host, JOBS, "databricks", "bundle", "plan", "-t", w["name"])
    else:
        run(host, JOBS, "databricks", "bundle", "deploy", "-t", w["name"], "--auto-approve")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--plan", action="store_true", help="show what a deploy would change; change nothing")
    p.add_argument("--only", help="only this served workspace's jobs (the hub is always deployed)")
    p.add_argument("--outputs", help="JSON {workspace: Terraform output self_service}, instead of reading the states")
    a = p.parse_args(argv)
    s = app_build.load()
    names = [n for n in s["spokes"] if not a.only or n == a.only]
    if a.only and not names:
        raise SystemExit(f"{a.only} is not a workspace the app serves: {', '.join(s['spokes']) or 'none'}.")
    spokes = app_build.served(s, json.loads(pathlib.Path(a.outputs).read_text()) if a.outputs else outputs(s["spokes"]))
    # First: the apps must exist before the jobs can grant them. The jobs are in the hub too, where
    # the apps' service principals are, so they grant the apps the hub deploy just found.
    app_ids = deploy_hub(s, spokes, a.plan)
    for w in spokes:
        if w["name"] in names:
            deploy_jobs(s, w, app_ids, a.plan)


if __name__ == "__main__":
    sys.exit(main())
