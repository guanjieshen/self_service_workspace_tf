"""scripts/app_deploy.py: the order and the rules of a deploy, with a stand-in for the CLI."""
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import app_deploy  # noqa: E402


class ProjectExists(unittest.TestCase):
    def test_a_deleted_project_stops_the_deploy_saying_how_to_clear_it(self):
        deleted = {"name": "projects/cd-self-service", "delete_time": "2026-11-02T23:32:47Z", "purge_time": "2026-11-09T23:32:47Z"}
        with mock.patch.object(app_deploy, "cli", return_value=deleted), self.assertRaises(SystemExit) as e:
            app_deploy.project_exists("https://h", "cd-self-service")
        self.assertIn("undelete-project", str(e.exception))
        self.assertIn("--purge", str(e.exception))

    def test_only_a_real_not_found_counts_as_missing(self):
        done = lambda code, err="": mock.Mock(returncode=code, stdout="", stderr=err)
        with mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, "Error: project projects/p does not exist")):
            self.assertIsNone(app_deploy.cli("https://h", "postgres", "get-project", "projects/p", missing_ok=True))
        for err in ("Error: cannot get access token: login.html", "dial tcp: i/o timeout", "PERMISSION_DENIED"):
            with self.subTest(err=err), mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, err)), \
                    self.assertRaises(SystemExit, msg="an outage is never read as 'not there'"):
                app_deploy.cli("https://h", "postgres", "get-project", "projects/p", missing_ok=True)
        with mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, "not found")), self.assertRaises(SystemExit):
            app_deploy.cli("https://h", "postgres", "get-project", "projects/p")   # without missing_ok, any failure stops

    def test_missing_and_present(self):
        with mock.patch.object(app_deploy, "cli", return_value=None):
            self.assertFalse(app_deploy.project_exists("https://h", "p"))
        with mock.patch.object(app_deploy, "cli", return_value={"name": "projects/p"}):
            self.assertTrue(app_deploy.project_exists("https://h", "p"))


class JobsGrantTheAppsTheHubFound(unittest.TestCase):
    """The jobs are in the hub, where the apps' service principals are: they grant the apps the hub
    deploy just found, on a first install too (before app_ids is set in hub.yaml)."""

    def run_main(self, app_ids):
        s = {"spokes": ["spoke"], "app_ids": app_ids}
        granted = []
        with mock.patch.object(app_deploy.app_build, "load", return_value=s), \
             mock.patch.object(app_deploy.app_build, "served", return_value=[{"name": "spoke"}]), \
             mock.patch.object(app_deploy, "outputs", return_value={}), \
             mock.patch.object(app_deploy, "deploy_hub", return_value=["new-1", "new-2"]), \
             mock.patch.object(app_deploy, "deploy_jobs", side_effect=lambda s, w, ids, plan: granted.append(ids)):
            app_deploy.main([])
        return granted

    def test_a_first_install_grants_the_new_apps(self):
        self.assertEqual(self.run_main({"self_service": None, "approvals": None}), [["new-1", "new-2"]])

    def test_and_later_the_same_apps(self):
        self.assertEqual(self.run_main({"self_service": "new-1", "approvals": "new-2"}), [["new-1", "new-2"]])


class FakeDatabricks:
    """The Databricks CLI as the deploy calls it: cli() answers, run() records commands."""

    def __init__(self, project=True, database=True, roles=("pipeline@x",), apps=("sp-1", "sp-2")):
        self.project, self.database, self.roles, self.apps = project, database, list(roles), apps
        self.ran, self.called = [], []

    def cli(self, host, *args, missing_ok=False):
        self.called.append(args)
        if args[:2] == ("current-user", "me"):
            return {"userName": "pipeline@x"}
        if args[:2] == ("postgres", "get-project"):
            return {"name": args[2]} if self.project else None
        if args[:2] == ("postgres", "list-roles"):
            return {"roles": [{"name": f"roles/{r}", "status": {"postgres_role": r}} for r in self.roles]}
        if args[:2] == ("postgres", "get-database"):
            return {"name": args[2]} if self.database else None
        if args[:2] == ("postgres", "get-endpoint"):
            return {"status": {"hosts": {"host": "ep-1.database.example"}}}
        if args[:2] == ("apps", "get"):
            return {"service_principal_client_id": self.apps[0] if args[2] == "cd-self-service" else self.apps[1]}
        return {}

    def run(self, host, cwd, *args):
        self.ran.append(" ".join(str(a) for a in args))


class DeployHub(unittest.TestCase):
    """deploy_hub: the order of a hub deploy, its first install, and the checks that stop it."""

    def deploy(self, fake, app_ids=None, plan=False, adopt=None):
        s = {"hub": {"host": "https://hub"}, "adopt": adopt or {}, "database": {"readers": ["reader@x"]},
             "app_ids": app_ids or {"self_service": None, "approvals": None},
             "app": {"name": "cd-self-service", "approvals": {"name": "cd-approvals"}, "database": {"project_id": "cd-self-service"}}}
        builds = []
        with mock.patch.object(app_deploy, "cli", fake.cli), mock.patch.object(app_deploy, "run", fake.run), \
                mock.patch.object(app_deploy, "bind_adopted"), \
                mock.patch.object(app_deploy.app_build, "build_hub", side_effect=lambda *a, **k: builds.append(k)):
            ids = app_deploy.deploy_hub(s, [], plan)
        return ids, builds

    def test_a_first_install_creates_the_project_then_points_the_apps_at_it(self):
        fake = FakeDatabricks(project=False)
        ids, builds = self.deploy(fake)
        self.assertEqual(builds, [{}, {"database": False}, {"database_host": "ep-1.database.example"}],
                         "an app cannot name a database that does not exist yet: without it first")
        deploys = [c for c in fake.ran if "bundle deploy" in c]
        self.assertEqual(len(deploys), 2)
        migrate = next(c for c in fake.ran if "migrate.py" in c)
        self.assertIn("--grant self_service=sp-1 --grant approvals=sp-2 --grant readers=reader@x", migrate)
        self.assertEqual([c for c in fake.ran if "bundle run" in c], ["databricks bundle run self_service -t hub",
                                                                   "databricks bundle run approvals -t hub"])
        self.assertEqual(ids, ["sp-1", "sp-2"])

    def test_an_existing_hub_deploys_once(self):
        fake = FakeDatabricks()
        self.deploy(fake, app_ids={"self_service": "sp-1", "approvals": "sp-2"})
        self.assertEqual(len([c for c in fake.ran if "bundle deploy" in c]), 1)

    def test_apps_that_are_not_the_ones_in_hub_yaml_stop_the_deploy(self):
        with self.assertRaisesRegex(SystemExit, "are not the apps' service principals"):
            self.deploy(FakeDatabricks(), app_ids={"self_service": "old-1", "approvals": "old-2"})

    def test_a_plan_changes_nothing(self):
        fake = FakeDatabricks()
        ids, _ = self.deploy(fake, app_ids={"self_service": "sp-1", "approvals": None}, plan=True)
        self.assertEqual(fake.ran, ["databricks bundle plan -t hub"])
        self.assertEqual(ids, ["sp-1"])
        self.assertFalse(any(c[:2] == ("postgres", "create-database") for c in fake.called))


class EnsureDatabase(unittest.TestCase):
    def test_the_database_is_created_owned_by_the_deploying_identity_with_a_role_per_reader(self):
        fake = FakeDatabricks(database=False)
        with mock.patch.object(app_deploy, "cli", fake.cli):
            app_deploy.ensure_database("https://hub", "projects/p/branches/production", "pipeline@x", ["reader@x"])
        create = next(c for c in fake.called if c[:2] == ("postgres", "create-database"))
        self.assertIn('"role": "roles/pipeline@x"', create[-1])
        self.assertTrue(any(c[:2] == ("postgres", "create-role") and "reader@x" in c[-1] for c in fake.called))

    def test_without_a_role_for_the_deploying_identity_it_stops(self):
        fake = FakeDatabricks(database=False, roles=())
        with mock.patch.object(app_deploy, "cli", fake.cli), self.assertRaisesRegex(SystemExit, "No Lakebase role for pipeline@x"):
            app_deploy.ensure_database("https://hub", "projects/p/branches/production", "pipeline@x", [])

    def test_an_existing_database_is_left_alone(self):
        fake = FakeDatabricks()
        with mock.patch.object(app_deploy, "cli", fake.cli):
            app_deploy.ensure_database("https://hub", "projects/p/branches/production", "pipeline@x", ["pipeline@x"])
        self.assertFalse(any(c[1] in ("create-database", "create-role") for c in fake.called))


class BindAdopted(unittest.TestCase):
    def test_only_what_the_bundle_does_not_manage_yet_is_bound(self):
        summary = mock.Mock(stdout='{"resources": {"apps": {"self_service": {"id": "cd-self-service"}, "approvals": {}}}}')
        ran = []
        with mock.patch.object(app_deploy.subprocess, "run", return_value=summary), \
                mock.patch.object(app_deploy, "run", side_effect=lambda host, cwd, *a: ran.append(" ".join(a))):
            app_deploy.bind_adopted("https://hub", {"self_service": "cd-self-service", "approvals": "cd-approvals"}, plan=False)
            self.assertEqual(ran, ["databricks bundle deployment bind approvals cd-approvals -t hub --auto-approve"])
            ran.clear()
            app_deploy.bind_adopted("https://hub", {"approvals": "cd-approvals"}, plan=True)
            self.assertEqual(ran, [], "a plan binds nothing")


class OutputsAndJobs(unittest.TestCase):
    def test_a_workspace_without_terraform_output_stops_the_deploy(self):
        done = lambda out, code=0: mock.Mock(returncode=code, stdout=out, stderr="no state")
        with mock.patch.object(app_deploy.subprocess, "run", return_value=done('Initializing...\n{"prefix": "fin"}')):
            self.assertEqual(app_deploy.outputs(["fin"]), {"fin": {"prefix": "fin"}}, "tf.sh's own lines before the JSON are skipped")
        for out, code in (("", 0), ('{"prefix": "fin"}', 1)):
            with self.subTest(code=code), mock.patch.object(app_deploy.subprocess, "run", return_value=done(out, code)), \
                    self.assertRaisesRegex(SystemExit, "apply its baseline first"):
                app_deploy.outputs(["fin"])

    def test_each_workspaces_job_is_planned_or_deployed_to_the_hub(self):
        ran = []
        with mock.patch.object(app_deploy.app_build, "build_jobs"), \
                mock.patch.object(app_deploy, "run", side_effect=lambda host, cwd, *a: ran.append((host, " ".join(a)))):
            s = {"hub": {"host": "https://hub"}}
            app_deploy.deploy_jobs(s, {"name": "fin", "host": "https://fin"}, ["sp-1"], plan=True)
            app_deploy.deploy_jobs(s, {"name": "fin", "host": "https://fin"}, ["sp-1"], plan=False)
        self.assertEqual(ran, [("https://hub", "databricks bundle plan -t fin"),
                               ("https://hub", "databricks bundle deploy -t fin --auto-approve")],
                         "each workspace's job, as its own target, in the hub")


class Main(unittest.TestCase):
    def test_the_hub_first_then_each_workspace_or_only_one(self):
        s = {"spokes": ["a", "b"], "app_ids": {"self_service": "sp-1", "approvals": "sp-2"}}
        order = []
        with mock.patch.object(app_deploy.app_build, "load", return_value=s), \
                mock.patch.object(app_deploy.app_build, "served", return_value=[{"name": "a"}, {"name": "b"}]), \
                mock.patch.object(app_deploy, "outputs", return_value={}), \
                mock.patch.object(app_deploy, "deploy_hub", side_effect=lambda *a: order.append("hub")), \
                mock.patch.object(app_deploy, "deploy_jobs", side_effect=lambda s, w, ids, plan: order.append(w["name"])):
            app_deploy.main([])
            self.assertEqual(order, ["hub", "a", "b"], "the apps must exist before the jobs can grant them")
            order.clear()
            app_deploy.main(["--only", "b"])
            self.assertEqual(order, ["hub", "b"])
            with self.assertRaisesRegex(SystemExit, "is not a workspace the app serves"):
                app_deploy.main(["--only", "c"])


if __name__ == "__main__":
    unittest.main()
