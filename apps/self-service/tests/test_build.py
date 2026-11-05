"""scripts/app_build.py: what the self-service bundles deploy, from config/self-service/ and the
workspaces the app serves (their files and Terraform outputs)."""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import app_build  # noqa: E402

HUB = """hub:
  name: central_hub
  host: https://adb-1000000000000001.1.azuredatabricks.net
  users_group: users
  approvals_group: platform-admins
  warehouse_id: null
database:
  readers: [reader@contoso.com]
app_ids:
  self_service: 11111111-1111-1111-1111-111111111111
  approvals: 22222222-2222-2222-2222-222222222222
adopt: {}
"""
WORKSPACES = {
    "central_hub": "prefix: hub\nhost: https://adb-1000000000000001.1.azuredatabricks.net\nself_service: false\n",
    "fin-citizen-dev": "prefix: fin\nhost: https://adb-2000000000000002.2.azuredatabricks.net\n",
    "ops-citizen-dev": "prefix: ops\nhost: https://adb-3000000000000003.3.azuredatabricks.net\n",
}
OUTPUTS = {
    "fin-citizen-dev": {"enabled": True, "prefix": "fin", "id": "2000000000000002", "host": "https://adb-2000000000000002.2.azuredatabricks.net",
                        "catalog": "fin_citizen_dev", "usage_policy_id": "policy-fin", "platform_admins": ["fin_platform_admins"]},
    "ops-citizen-dev": {"enabled": True, "prefix": "ops", "id": "3000000000000003", "host": "https://adb-3000000000000003.3.azuredatabricks.net",
                        "catalog": "ops_citizen_dev", "usage_policy_id": None},
}


class Builds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        (self.tmp / "config").mkdir()
        shutil.copy(ROOT / "config/self-service/app.yaml", self.tmp / "config/app.yaml")   # the repository's own settings
        (self.tmp / "config/hub.yaml").write_text(HUB)
        (self.tmp / "workspaces").mkdir()
        for name, text in WORKSPACES.items():
            (self.tmp / "workspaces" / f"{name}.yaml").write_text(text)
        (self.tmp / "workspaces/_example.yaml").write_text("prefix: xyz\n")
        self.s = app_build.load(self.tmp / "config", self.tmp / "workspaces")
        self.spokes = app_build.served(self.s, OUTPUTS)

    def read(self, path):
        return json.loads(path.read_text())

    def test_the_served_workspaces_are_the_files_without_self_service_false(self):
        self.assertEqual(self.s["spokes"], ["fin-citizen-dev", "ops-citizen-dev"], "not the hub, not _example")
        self.assertEqual([(w["name"], w["bu"], w["catalog"]) for w in self.spokes],
                         [("fin-citizen-dev", "FIN", "fin_citizen_dev"), ("ops-citizen-dev", "OPS", "ops_citizen_dev")])

    def test_a_workspace_without_a_terraform_output_stops_the_build(self):
        with self.assertRaises(SystemExit) as e:
            app_build.served(self.s, {"fin-citizen-dev": OUTPUTS["fin-citizen-dev"]})
        self.assertIn("ops-citizen-dev", str(e.exception))
        with self.assertRaises(SystemExit):
            app_build.served(self.s, {**OUTPUTS, "ops-citizen-dev": {**OUTPUTS["ops-citizen-dev"], "catalog": None}})

    def test_each_app_lists_every_served_workspace(self):
        out = app_build.build_hub(self.s, self.spokes, database_host="ep-example-1.database.canadacentral.azuredatabricks.net", root=self.tmp)
        config, approvals = self.read(out / "self-service/config.json"), self.read(out / "approvals/config.json")
        self.assertEqual(approvals, {**config, "mode": "approvals"})
        self.assertEqual(config["workspaces"], [
            {"name": "fin-citizen-dev", "bu": "FIN", "host": "https://adb-2000000000000002.2.azuredatabricks.net", "id": "2000000000000002", "catalog": "fin_citizen_dev"},
            {"name": "ops-citizen-dev", "bu": "OPS", "host": "https://adb-3000000000000003.3.azuredatabricks.net", "id": "3000000000000003", "catalog": "ops_citizen_dev"}])
        self.assertEqual(config["database"]["host"], "ep-example-1.database.canadacentral.azuredatabricks.net")
        self.assertTrue(config["links"]["discover"].startswith("{host}/"), "the app fills in each person's own workspace, not the hub's")
        self.assertEqual(config["ai"], {"model": self.s["app"]["ai_model"]}, "one model for every AI feature")
        for skipped in ("tests", "db", "AGENTS.md", "__pycache__"):
            self.assertFalse((out / "self-service" / skipped).exists(), skipped)

    def test_an_app_yaml_from_1_0_keeps_its_summary_model_as_the_ai_model(self):
        self.assertEqual(app_build.ai_model({"ai_summary": {"model": "system.ai.old"}}), "system.ai.old")
        self.assertEqual(app_build.ai_model({"ai_model": "system.ai.new", "ai_summary": {"model": "system.ai.old"}}), "system.ai.new")
        self.assertEqual(app_build.ai_model({"ai_summary": {"model": None}}), "", "null: no AI")

    def test_the_hub_target(self):
        out = app_build.build_hub(self.s, self.spokes, root=self.tmp)
        t = self.read(out / "target.yml")["targets"]["hub"]
        self.assertEqual(t["workspace"], {"host": "https://adb-1000000000000001.1.azuredatabricks.net", "root_path": "/Workspace/Admin/self-service/bundle/hub"})
        apps = t["resources"]["apps"]
        self.assertEqual(apps["self_service"]["permissions"], [{"level": "CAN_USE", "group_name": "users"}])
        self.assertEqual(apps["approvals"]["permissions"], [{"level": "CAN_USE", "group_name": "platform-admins"}])
        self.assertEqual([r["name"] for r in apps["self_service"]["resources"]], ["database"], "no jobs: they are in other workspaces")
        first = app_build.hub_target(self.s, database=False)["targets"]["hub"]["resources"]["apps"]
        self.assertEqual(first["self_service"]["resources"], [], "a first install's first pass: no database yet")

    def test_each_served_workspace_gets_its_schema_job_in_the_hub(self):
        out = app_build.build_jobs(self.s, self.spokes[0], ["11111111-1111-1111-1111-111111111111"], root=self.tmp)
        t = self.read(out / "target.yml")["targets"]["fin-citizen-dev"]
        self.assertEqual(t["workspace"], {"host": "https://adb-1000000000000001.1.azuredatabricks.net",
                                          "root_path": "/Workspace/Admin/self-service/bundle/jobs/fin-citizen-dev"},
                         "in the hub, each workspace's job with its own state")
        self.assertEqual(t["variables"], {"business_unit": "FIN"})
        jobs = t["resources"]["jobs"]
        self.assertEqual(set(jobs), {"personal_schema"}, "the folder job is not deployed for now")
        self.assertFalse((out / "team_folder.py").exists())
        self.assertEqual(jobs["personal_schema"]["tags"], {"cd_catalog": "fin_citizen_dev", "cd_prefix": "cd_", "cd_workspace": "fin-citizen-dev"})
        self.assertEqual(jobs["personal_schema"]["permissions"], [{"level": "CAN_MANAGE_RUN", "service_principal_name": "11111111-1111-1111-1111-111111111111"}])
        self.assertEqual(jobs["personal_schema"]["usage_policy_id"], "policy-fin", "on the workspace's usage policy (bound to the hub too)")
        schema = (out / "personal_schema.py").read_text()
        self.assertNotIn("${", schema)
        self.assertIn('allowed_catalogs = ["fin_citizen_dev"]', schema)
        self.assertNotIn('comment_model = "', schema, "a run parameter (the app's Settings), not written in")
        ops = app_build.jobs_target(self.s, self.spokes[1], [])["targets"]["ops-citizen-dev"]["resources"]["jobs"]
        self.assertNotIn("usage_policy_id", ops["personal_schema"], "no usage policy: none set")

    def test_what_the_jobs_allow_follows_terraform_never_a_fixed_value(self):
        """The notebook's settings come from the workspace's Terraform output (and app.yaml): change
        the catalog in Terraform, and the next deploy writes the new one in."""
        moved = app_build.served(self.s, {**OUTPUTS, "fin-citizen-dev": {**OUTPUTS["fin-citizen-dev"], "catalog": "fin_moved"}})
        out = app_build.build_jobs(self.s, moved[0], [], root=self.tmp)
        schema = (out / "personal_schema.py").read_text()
        self.assertIn('allowed_catalogs = ["fin_moved"]', schema)
        self.assertNotIn("fin_citizen_dev", schema)
        self.assertNotIn("${", schema, "every setting filled in at build")

    def test_the_build_never_grants_on_what_terraform_owns(self):
        """Catalogs, warehouses' permissions, usage policies and workspace assignment are Terraform's:
        the bundles only refer to them."""
        hub = json.dumps(app_build.hub_target(self.s))
        spoke = json.dumps(app_build.jobs_target(self.s, self.spokes[0], ["x"]))
        for text in (hub, spoke):
            for owned in ("catalogs", "grants", "permission_assignment", "budget_polic", "sql_warehouses", "schemas"):
                self.assertNotIn(owned, text)

    def test_settings_that_would_fail_later_are_refused(self):
        for change, setting in (
                (lambda s: s["hub"].update(host="adb-1.azuredatabricks.net"), "hub.host"),
                (lambda s: s["app"].update(ai_check="maybe"), "ai_check"),
                (lambda s: s["app"].update(ai_model="x'); DROP"), "ai_model"),
                (lambda s: s["database"].update(readers=["x; DROP TABLE y"]), "database.readers"),
                (lambda s: s["app_ids"].update(self_service="not-an-id"), "app_ids"),
                (lambda s: s["app"].update(bu_lookup={"function": "a.b.c"}), "warehouse_id"),
                (lambda s: s["adopt"].update(database="cd-self-service"), "adopt.database")):
            with self.subTest(setting=setting):
                bad = json.loads(json.dumps(self.s))
                change(bad)
                with self.assertRaises(SystemExit) as e:
                    app_build.check(bad)
                self.assertIn(setting, str(e.exception))

    def test_the_repositorys_own_settings_load_or_say_what_to_fill_in(self):
        """This repository's hub.yaml is filled in; a release's is blank until set up."""
        try:
            s = app_build.load()
        except SystemExit as e:
            self.assertIn("hub.host", str(e))
            return
        self.assertTrue(s["hub"]["host"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
