"""scripts/preflight.py: read-only checks before a workspace's first apply, against a fake API."""
import contextlib
import io
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import load

pf = load("preflight")

GIT = 'settings:\n  git:\n    allowed_urls:\n      - "https://github.com/fin/"\n'
GROUPS = "groups:\n" + "".join(f"  {k}: fin_{k}\n" for k in ("users", "explorer", "builder", "publisher"))
ADMIN = {"userName": "sp-terraform", "groups": [{"display": "admins"}, {"display": "users"}]}
ACCOUNT_GROUPS = {"fin_users", "fin_explorer", "fin_builder", "fin_publisher", "fin_platform_admins"}


class FakeApi:
    """GET paths -> (json, error). Everything is ready unless a test changes it."""

    def __init__(self, me=ADMIN, account_groups=ACCOUNT_GROUPS, local_groups=(), storage_root="abfss://ms@x/",
                 catalog_exists=False, legacy_disabled=False, hive=(), mounts=(), clusters=(),
                 empty_groups=(), billing_admins=("users/sp-terraform",), rule_set_error=None):
        self.me, self.account_groups, self.local_groups = me, set(account_groups), set(local_groups)
        self.empty_groups, self.billing_admins, self.rule_set_error = set(empty_groups), list(billing_admins), rule_set_error
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
        if path.startswith("/api/2.0/preview/accounts/access-control/rule-sets"):
            if self.rule_set_error:
                return None, self.rule_set_error
            return {"grant_rules": [{"role": "roles/billing.admin", "principals": self.billing_admins}]}, None
        for prefix, groups in (("/api/2.0/account/scim/v2/Groups", self.account_groups),
                               ("/api/2.0/preview/scim/v2/Groups", self.local_groups)):
            if path.startswith(prefix):
                hit = [g for g in groups if f"%22{g}%22" in path]
                return {"totalResults": len(hit), "Resources": [
                    {"displayName": g, "members": [] if g in self.empty_groups else [{"value": "1"}]} for g in hit]}, None
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


class Base(unittest.TestCase):
    """A workspace file and a fake API; no tests of its own."""
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        # The workspace's file, composed from parts so a test can change one.
        self.parts = {"workspace": "prefix: fin\nhost: https://adb-123.1.azuredatabricks.net\n",
                      "settings": GIT,       # the baseline's Git allowlist is a placeholder
                      "access": GROUPS}      # each workspace names its persona groups
        self.write()
        # Outside CI by default (the runner sets GITHUB_ACTIONS); the CI test sets it itself.
        patches = [mock.patch.object(pf.wsf, "WORKSPACES", self.root), mock.patch.object(pf.wsf, "DEV_WORKSPACES", self.root / "none"),
                   mock.patch.dict(pf.os.environ, {"GITHUB_ACTIONS": ""})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.root)

    def write(self):
        (self.root / "fin-dev.yaml").write_text("".join(self.parts.values()))

    def set(self, part, text):
        self.parts[part] = text
        self.write()

    def run_checks(self, api):
        return pf.checks("fin-dev", api)

    def levels(self, results, level):
        return [m for l, m in results if l == level]


class Preflight(Base):
    def test_a_ready_workspace_has_no_errors_or_warnings(self):
        results = self.run_checks(FakeApi())
        self.assertEqual(self.levels(results, "error") + self.levels(results, "warning"), [])
        self.assertIn("signed in as sp-terraform, a workspace admin", self.levels(results, "ok"))

    def test_errors_keep_the_reason_and_drop_credentials(self):
        leak = 'cannot sign in to https://adb-1.1.azuredatabricks.net: failed during request visitor: github-oidc-azure auth: not configured. Config: host=https://adb-1.1.azuredatabricks.net, account_id=acct, actions_id_token_request_url=https://x/idtoken?api-version=2.0, actions_id_token_request_token=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvIn0.c2lnbmF0dXJl. Env: DATABRICKS_HOST'
        short = pf.short_error(leak)
        self.assertNotIn("eyJ", short)
        self.assertNotIn("Config:", short, "the configuration dump is dropped")
        self.assertTrue(short.startswith("cannot sign in to https://adb-1.1.azuredatabricks.net"))
        self.assertEqual(pf.redact("x token=abc, client_secret=d e"), "x token=***, client_secret=*** e")

    def test_in_ci_without_the_setup_it_says_which_step(self):
        with mock.patch.dict(pf.os.environ, {"GITHUB_ACTIONS": "true", "ARM_CLIENT_ID": "", "ARM_TENANT_ID": "t"}):
            api = FakeApi()
            results = self.run_checks(api)
        self.assertEqual(len(results), 1)
        self.assertIn("AZURE_CLIENT_ID are not set", results[0][1])
        self.assertIn("docs/SETUP.md, steps 4 and 5", results[0][1])
        self.assertEqual(api.paths, [], "nothing is called without an identity")
        with mock.patch.dict(pf.os.environ, {"GITHUB_ACTIONS": "true", "ARM_CLIENT_ID": "c", "ARM_TENANT_ID": "t"}):
            self.assertEqual(self.levels(self.run_checks(FakeApi()), "error"), [], "with the variables set, the checks run")

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
        self.set("access", "groups:\n  builder: data-builders   # Entra\n")
        api = FakeApi(account_groups=(ACCOUNT_GROUPS - {"fin_builder"}) | {"data-builders"})
        self.assertEqual(self.levels(self.run_checks(api), "error"), [])

    def test_a_persona_without_a_group_is_skipped(self):
        self.set("access", "groups:\n  explorer: fin_explorer\n")
        results = self.run_checks(FakeApi())
        self.assertEqual(self.levels(results, "error"), [])
        oks = " ".join(self.levels(results, "ok"))
        for key in ("users", "builder", "publisher"):
            self.assertIn(f"no {key} group: skipped", oks)
        self.assertIn("account group fin_platform_admins (platform_admins)", oks, "the baseline's platform admins group")

    def test_catalog_storage(self):
        self.assertIn("the metastore has no storage root", " ".join(self.levels(self.run_checks(FakeApi(storage_root=None)), "error")))
        self.set("catalog", "catalog:\n  storage_root: abfss://catalogs@acct.dfs.core.windows.net/fin\n")
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
        self.set("settings", GIT + "  disable_legacy_access: null\n")
        api = FakeApi(hive=["sales"])
        self.run_checks(api)
        self.assertFalse(any("hive_metastore" in p for p in api.paths), "left alone: nothing to check")



class Guardrails(Base):
    """The platform admins group has members; the identity may create usage policies."""

    def setUp(self):
        super().setUp()
        # The baseline's account and usage policy, whatever the repository's own config/defaults/ says.
        real = pf.wsf.workspace_info
        p = mock.patch.object(pf.wsf, "workspace_info", lambda f: {**real(f), "account": "acct-1", "serverless_policy": True})
        p.start()
        self.addCleanup(p.stop)

    def messages(self, api, level):
        return [m for l, m in self.run_checks(api) if l == level]

    def test_an_empty_platform_admins_group_is_a_warning(self):
        warnings = self.messages(FakeApi(empty_groups={"fin_platform_admins"}), "warning")
        self.assertTrue(any("fin_platform_admins (platform_admins) has no members" in w for w in warnings), warnings)
        self.assertFalse(any("has no members" in w for w in self.messages(FakeApi(), "warning")))
        self.assertFalse(any("has no members" in w for w in self.messages(FakeApi(empty_groups={"fin_builder"}), "warning")),
                         "only the platform admins group must have members")

    def test_creating_usage_policies_needs_billing_admin(self):
        self.assertTrue(any("may create usage policies" in m for m in self.messages(FakeApi(), "ok")))
        warnings = self.messages(FakeApi(billing_admins=["users/someone-else"]), "warning")
        self.assertTrue(any("Billing admin" in w and "step 6" in w for w in warnings), "locally, a warning: " + str(warnings))
        with mock.patch.dict(pf.os.environ, {"GITHUB_ACTIONS": "true", "ARM_CLIENT_ID": "x", "ARM_TENANT_ID": "y"}):
            errors = self.messages(FakeApi(billing_admins=["users/someone-else"]), "error")
        self.assertTrue(any("Billing admin" in e for e in errors), "in CI, an error before the plan: " + str(errors))
        via_group = FakeApi(billing_admins=["groups/admins"])
        self.assertTrue(any("may create usage policies" in m for m in self.messages(via_group, "ok")), "a group it is in counts")
        self.assertTrue(any("could not check" in w for w in self.messages(FakeApi(rule_set_error="forbidden"), "warning")),
                        "a rule set it cannot read is a warning, not an error")

    def test_no_check_without_a_usage_policy(self):
        with mock.patch.object(pf.wsf, "workspace_info", lambda f: {"prefix": "fin", "host": "h", "catalog": None,
                                                                     "account": "acct-1", "serverless_policy": False}):
            api = FakeApi(billing_admins=[])
            self.run_checks(api)
            self.assertFalse(any("rule-sets" in p for p in api.paths))



class RedactionAgrees(unittest.TestCase):
    """preflight.py and plan-comment.js redact the same secrets the same way."""

    @unittest.skipUnless(shutil.which("node"), "needs node (the Tests job sets it up)")
    def test_python_and_javascript_redact_alike(self):
        import subprocess
        sample = ("sign-in failed: actions_id_token_request_token=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvIn0.c2ln, "
                  "client_secret=abc123 password=hunter2 ok=1")
        js = subprocess.run(["node", "-e", "process.stdout.write(require(process.argv[1]).redact(process.argv[2]))",
                             str(pf.wsf.ROOT / ".github/scripts/plan-comment.js"), sample], capture_output=True, text=True, check=True).stdout
        self.assertEqual(pf.redact(sample), js)
        self.assertNotIn("eyJ", js)
        self.assertNotIn("hunter2", js)



class OutFiles(Base):
    """--out writes the problems, and every finding next to it, without overwriting either."""

    def test_both_files_whatever_the_name(self):
        for name, all_name in ((".plans/ws.preflight.txt", ".plans/ws.preflight-all.txt"), ("report.txt", "report-all.txt")):
            with self.subTest(name=name), mock.patch.object(pf, "cli_get", lambda profile: FakeApi()), \
                    mock.patch.dict(pf.os.environ, {"DATABRICKS_HOST": "https://adb-1.1.azuredatabricks.net"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                out = self.root / name
                pf.main(["fin-dev", "--out", str(out)])
                self.assertTrue(out.exists() and (self.root / all_name).exists())
                self.assertIn("ok:", (self.root / all_name).read_text(), "every finding, ok ones too")
                self.assertNotIn("ok:", out.read_text(), "only the problems")


if __name__ == "__main__":
    unittest.main()
