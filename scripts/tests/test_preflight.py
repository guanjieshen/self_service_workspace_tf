"""scripts/preflight.py: read-only checks before a workspace's first apply, against a fake API."""
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import load

pf = load("preflight")

GIT = 'settings:\n  git:\n    allowed_urls:\n      - "https://github.com/fin/"\n'
ADMIN = {"userName": "sp-terraform", "groups": [{"display": "admins"}, {"display": "users"}]}
ACCOUNT_GROUPS = {"fin_users", "fin_explorer", "fin_builder", "fin_publisher", "fin_platform_admins"}


class FakeApi:
    """GET paths -> (json, error). Everything is ready unless a test changes it."""

    def __init__(self, me=ADMIN, account_groups=ACCOUNT_GROUPS, local_groups=(), storage_root="abfss://ms@x/",
                 catalog_exists=False, legacy_disabled=False, hive=(), mounts=(), clusters=()):
        self.me, self.account_groups, self.local_groups = me, set(account_groups), set(local_groups)
        self.storage_root, self.catalog_exists, self.legacy_disabled = storage_root, catalog_exists, legacy_disabled
        self.hive, self.mounts, self.clusters = hive, mounts, clusters
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)
        if path.startswith("/api/2.0/preview/scim/v2/Me"):
            return (self.me, None) if self.me else (None, "Unauthorized")
        if path == "/api/2.1/unity-catalog/current-metastore-assignment":
            return {"metastore_id": "ms-1"}, None
        if path == "/api/2.1/unity-catalog/metastores/ms-1":
            return {"name": "ms", "storage_root": self.storage_root}, None
        for prefix, groups in (("/api/2.0/account/scim/v2/Groups", self.account_groups),
                               ("/api/2.0/preview/scim/v2/Groups", self.local_groups)):
            if path.startswith(prefix):
                hit = [g for g in groups if f"%22{g}%22" in path]
                return {"totalResults": len(hit)}, None
        if path.startswith("/api/2.1/unity-catalog/catalogs/"):
            return ({"name": path.rsplit("/", 1)[1]}, None) if self.catalog_exists else (None, "does not exist")
        if path == "/api/2.1/settings/disable_legacy_access":
            return {"disable_legacy_access": {"value": self.legacy_disabled}}, None
        if path.startswith("/api/2.1/unity-catalog/schemas?catalog_name=hive_metastore"):
            return {"schemas": [{"name": n} for n in self.hive]}, None
        if path.startswith("/api/2.0/dbfs/list"):
            return {"files": [{"path": p} for p in self.mounts]}, None
        if path.startswith("/api/2.1/clusters/list"):
            return {"clusters": [{"cluster_name": n, "data_security_mode": m} for n, m in self.clusters]}, None
        raise AssertionError(f"unexpected GET {path}")


class Preflight(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.d = self.root / "fin-dev"
        self.d.mkdir()
        (self.d / "workspace.yaml").write_text(
            "bu: fin\nlob: FIN\naccount_id: acct\nhost: https://adb-123.1.azuredatabricks.net\nci: true\n")
        (self.d / "settings.yaml").write_text(GIT)   # the baseline's Git allowlist is a placeholder
        patches = [mock.patch.object(pf.wsf, "WORKSPACES", self.root), mock.patch.object(pf.wsf, "DEV_WORKSPACES", self.root / "none")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.root)

    def run_checks(self, api):
        return pf.checks("fin-dev", api)

    def levels(self, results, level):
        return [m for l, m in results if l == level]

    def test_a_ready_workspace_has_no_errors_or_warnings(self):
        results = self.run_checks(FakeApi())
        self.assertEqual(self.levels(results, "error") + self.levels(results, "warning"), [])
        self.assertIn("signed in as sp-terraform, a workspace admin", self.levels(results, "ok"))

    def test_the_git_allowlist_placeholder_is_flagged(self):
        (self.d / "settings.yaml").unlink()
        warnings = self.levels(self.run_checks(FakeApi()), "warning")
        self.assertEqual(len(warnings), 1)
        self.assertIn("still has the placeholder https://github.com/<org>/", warnings[0])

    def test_no_sign_in_stops_at_once(self):
        results = self.run_checks(FakeApi(me=None))
        self.assertEqual(len(results), 1)
        self.assertIn("cannot sign in", results[0][1])

    def test_not_an_admin(self):
        results = self.run_checks(FakeApi(me={"userName": "sp", "groups": [{"display": "users"}]}))
        self.assertIn("sp is not a workspace admin: make it one (docs/SETUP.md, step 6)", self.levels(results, "error"))

    def test_groups_must_be_account_groups(self):
        results = self.run_checks(FakeApi(account_groups=ACCOUNT_GROUPS - {"fin_builder", "fin_explorer"},
                                          local_groups={"fin_builder"}))
        errors = self.levels(results, "error")
        self.assertEqual(len(errors), 2)
        self.assertIn("fin_builder (builder) exists only in this workspace", errors[0] + errors[1])
        self.assertIn("fin_explorer (explorer) does not exist in the account", errors[0] + errors[1])

    def test_a_workspace_names_its_own_groups(self):
        (self.d / "access.yaml").write_text("groups:\n  builder: data-builders   # Entra\n")
        api = FakeApi(account_groups=(ACCOUNT_GROUPS - {"fin_builder"}) | {"data-builders"})
        self.assertEqual(self.levels(self.run_checks(api), "error"), [])

    def test_unmanaged_groups_only_warn(self):
        (self.d / "access.yaml").write_text("manage:\n  group_assignment: false\n  catalog_grants: false\n")
        results = self.run_checks(FakeApi(account_groups=()))
        self.assertEqual(self.levels(results, "error"), [])
        self.assertEqual(len(self.levels(results, "warning")), 5)

    def test_catalog_storage(self):
        self.assertIn("the metastore has no storage root", " ".join(self.levels(self.run_checks(FakeApi(storage_root=None)), "error")))
        (self.d / "catalog.yaml").write_text("catalog:\n  storage_root: abfss://catalogs@acct.dfs.core.windows.net/fin\n")
        self.assertEqual(self.levels(self.run_checks(FakeApi(storage_root=None)), "error"), [])

    def test_an_existing_catalog_needs_no_storage(self):
        self.assertEqual(self.levels(self.run_checks(FakeApi(storage_root=None, catalog_exists=True)), "error"), [])

    def test_legacy_uses_are_listed_before_the_one_way_switch(self):
        api = FakeApi(hive=["default", "sales"], mounts=["/mnt/raw"], clusters=[("old", "NONE"), ("new", "USER_ISOLATION")])
        warnings = self.levels(self.run_checks(api), "warning")
        self.assertEqual(len(warnings), 1)
        for text in ("permanent after 30 days", "sales", "/mnt/raw", "old"):
            self.assertIn(text, warnings[0])
        self.assertNotIn("new", warnings[0].split("clusters")[1])

    def test_legacy_checks_skipped_once_disabled_or_left_alone(self):
        api = FakeApi(legacy_disabled=True, hive=["sales"])
        self.assertEqual(self.levels(self.run_checks(api), "warning"), [])
        (self.d / "settings.yaml").write_text(GIT + "  disable_legacy_access: null\n")
        api = FakeApi(hive=["sales"])
        self.run_checks(api)
        self.assertFalse(any("hive_metastore" in p for p in api.paths), "left alone: nothing to check")


if __name__ == "__main__":
    unittest.main()
