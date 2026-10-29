"""scripts/plan-guard.py: which plan changes are flagged as hard to undo."""
import contextlib
import io
import json
import sys
import tempfile
import unittest

from helpers import SCRIPTS, change, load

guard = load("plan-guard")


def run(*changes, released=None, preflight=None):
    """(exit code, printed text) for a plan with these resource changes (and preflight's findings)."""
    stdin, out = sys.stdin, io.StringIO()
    plan = {"resource_changes": list(changes)}
    if released is not None:
        plan["planned_values"] = {"outputs": {"released_addresses": {"value": released}}}
    sys.stdin = io.StringIO(json.dumps(plan))
    try:
        with contextlib.redirect_stdout(out):
            argv = []
            if preflight is not None:
                f = tempfile.NamedTemporaryFile("w", suffix=".preflight-all.txt", delete=False)
                f.write(preflight)
                f.close()
                argv = ["--preflight", f.name]
            code = guard.main(argv)
    finally:
        sys.stdin = stdin
    return code, out.getvalue()


class PlanGuard(unittest.TestCase):
    def test_safe_changes_pass(self):
        code, out = run(
            change("databricks_sql_endpoint", ["create"]),
            change("databricks_sql_endpoint", ["update"]),
            change("databricks_permissions", ["update"]),
            change("databricks_workspace_file", ["delete"]),
        )
        self.assertEqual((code, out), (0, ""))

    def test_every_protected_type_is_flagged_on_delete_and_replace(self):
        for rtype in guard.PROTECTED:
            with self.subTest(rtype=rtype):
                code, out = run(change(rtype, ["delete"]))
                self.assertEqual(code, 2)
                self.assertIn("DELETE " + guard.PROTECTED[rtype], out)
                code, out = run(change(rtype, ["delete", "create"]))
                self.assertIn("REPLACE " + guard.PROTECTED[rtype], out)

    def test_default_catalog_change(self):
        code, out = run(change("databricks_default_namespace_setting", ["update"]))
        self.assertEqual(code, 2)
        self.assertIn("CHANGE the default catalog", out)
        self.assertEqual(run(change("databricks_default_namespace_setting", ["create"]))[0], 0)

    def test_compliance_security_profile_is_one_way(self):
        code, out = run(change("databricks_compliance_security_profile_workspace_setting", ["create"]))
        self.assertEqual(code, 2)
        self.assertIn("ONE-WAY", out)

    def test_disable_legacy_access_only_when_turned_on(self):
        on = {"disable_legacy_access": [{"value": True}]}
        off = {"disable_legacy_access": [{"value": False}]}
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["create"], after=on))[0], 2)
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["update"], after=on))[0], 2)
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["create"], after=off))[0], 0)

    def test_disable_legacy_access_on_a_new_workspace_with_preflight_evidence(self):
        on = {"disable_legacy_access": [{"value": True}]}
        clean = "ok: signed in\nok: nothing found that still uses legacy access (Hive metastore, DBFS mounts, legacy clusters)\n"
        busy = "warning: the baseline disables legacy access, ... this workspace still has Hive metastore schemas: sales\n"
        code, out = run(change("databricks_disable_legacy_access_setting", ["create"], after=on), preflight=clean)
        self.assertEqual(code, 0, "a first apply where preflight found nothing using legacy access is not flagged")
        self.assertIn("Not flagged", out)
        self.assertIn("Preflight found nothing that still uses it", out)
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["create"], after=on), preflight=busy)[0], 2,
                         "flagged when preflight found something that uses legacy access")
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["update"], after=on), preflight=clean)[0], 2,
                         "flagged when it was managed and turned on later (an update), whatever preflight says")
        self.assertEqual(run(change("databricks_disable_legacy_access_setting", ["create"], after=on), preflight="")[0], 2,
                         "flagged when preflight did not report its finding")

    def test_the_guard_matches_preflights_wording(self):
        src = (SCRIPTS / "preflight.py").read_text()
        self.assertIn(f'("ok", "{guard.NOTHING_USES_LEGACY[len("ok: "):]}', src,
                      "scripts/preflight.py must write the line the guard looks for")

    def test_all_warnings_are_listed(self):
        code, out = run(change("databricks_directory", ["delete"], name="a"), change("databricks_catalog", ["delete"], name="b"))
        self.assertEqual(out.count("  - "), 2)


class Loosening(unittest.TestCase):
    """Changes that weaken security need the same approval as hard-to-undo ones."""

    def flagged(self, rc, word):
        code, out = run(rc)
        self.assertEqual(code, 2, out)
        self.assertIn(word, out)

    def clean(self, *rcs):
        code, out = run(*rcs)
        self.assertEqual((code, out), (0, ""))

    def test_security_settings_turned_off_or_deleted(self):
        legacy_on = {"disable_legacy_access": [{"value": True}]}
        self.flagged(change("databricks_disable_legacy_access_setting", ["update"], before=legacy_on,
                            after={"disable_legacy_access": [{"value": False}]}), "TURN OFF disable legacy access")
        self.flagged(change("databricks_disable_legacy_access_setting", ["delete"], before=legacy_on), "returns to the platform default")
        gw = {"name": "enforce_ai_gateway_v3_only"}
        self.flagged(change("databricks_workspace_setting_v2", ["update"], before={**gw, "boolean_val": {"value": True}},
                            after={**gw, "boolean_val": {"value": False}}), "TURN OFF Enforce Unity Gateway")
        self.flagged(change("databricks_restrict_workspace_admins_setting", ["delete"],
                            before={"restrict_workspace_admins": [{"status": "RESTRICT_TOKENS_AND_JOB_RUN_AS"}]}), "restrict workspace admins")

    def test_settings_v2_are_told_apart_by_name(self):
        # One resource type for many settings: only the security ones are flagged.
        v2 = lambda name, before, after, actions=("update",): change("databricks_workspace_setting_v2", list(actions),
                                                                      before={"name": name, **before}, after={"name": name, **after})
        self.flagged(v2("sql_results_download", {"boolean_val": {"value": False}}, {"boolean_val": {"value": True}}),
                     "SQL results download")
        self.flagged(v2("collaboration_platform_connectivity", {"collaboration_platform_connectivity": {"connectivity": "DENY_ALL"}},
                        {"collaboration_platform_connectivity": {"connectivity": "ALLOW_ALL"}}), "collaboration platforms")
        self.flagged(v2("collaboration_platform_message_visibility", {"boolean_val": {"value": False}}, {"boolean_val": {"value": True}}),
                     "collaboration platform answers")
        self.clean(v2("workspace_label", {"workspace_label": {"label": "DEV", "color": "lime"}},
                      {"workspace_label": {"label": "PROD", "color": "coral"}}))
        self.clean(v2("default_warehouse_id", {"string_val": {"value": "a"}}, {"string_val": {"value": "b"}}))
        self.clean(v2("sql_results_download", {"boolean_val": {"value": True}}, {"boolean_val": {"value": False}}))

    def test_workspace_configuration_loosened(self):
        self.flagged(change("databricks_workspace_conf", ["update"], before={"custom_config": {"enforceUserIsolation": "true"}},
                            after={"custom_config": {"enforceUserIsolation": "false"}}), "LOOSEN workspace setting enforceUserIsolation")
        self.flagged(change("databricks_workspace_conf", ["update"], before={"custom_config": {"enableResultsDownloading": "false"}},
                            after={"custom_config": {"enableResultsDownloading": "true"}}), "enableResultsDownloading")
        self.flagged(change("databricks_workspace_conf", ["update"], before={"custom_config": {"enableUploadDataUis": "false"}},
                            after={"custom_config": {"enableUploadDataUis": "true"}}), "enableUploadDataUis")
        self.flagged(change("databricks_workspace_conf", ["update"], before={"custom_config": {"maxTokenLifetimeDays": "90"}},
                            after={"custom_config": {"maxTokenLifetimeDays": "365"}}), "90 -> 365 days")

    def test_data_exposed(self):
        self.flagged(change("databricks_catalog", ["update"], before={"name": "c", "isolation_mode": "ISOLATED"},
                            after={"name": "c", "isolation_mode": "OPEN"}), "OPEN catalog c")
        self.flagged(change("databricks_grants", ["update"], before={"catalog": "c", "grant": [{"principal": "g"}]},
                            after={"catalog": "c", "grant": [{"principal": "g"}, {"principal": "account users"}]}), "GRANT account users")
        self.flagged(change("databricks_grants", ["create"], after={"schema": "c.s", "grant": [{"principal": "users"}]}), "on c.s")

    def test_more_token_creators_and_cluster_creation(self):
        self.flagged(change("databricks_permissions", ["update"], before={"authorization": "tokens", "access_control": [{"group_name": "a"}]},
                            after={"authorization": "tokens", "access_control": [{"group_name": "a"}, {"group_name": "b"}]}), "adds b")
        users = {**change("databricks_entitlements", ["update"], before={"allow_cluster_create": False},
                          after={"allow_cluster_create": True}), "address": "module.personas.databricks_entitlements.users[0]"}
        self.flagged(users, "unrestricted cluster creation")

    def test_not_flagged(self):
        self.clean(
            # First-time management: there is no earlier value to weaken.
            change("databricks_workspace_conf", ["create"], after={"custom_config": {"enableTokensConfig": "true"}}),
            change("databricks_disable_legacy_access_setting", ["create"], after={"disable_legacy_access": [{"value": False}]}),
            # Tightening.
            change("databricks_workspace_conf", ["update"], before={"custom_config": {"enforceUserIsolation": "false"}},
                   after={"custom_config": {"enforceUserIsolation": "true"}}),
            change("databricks_workspace_conf", ["update"], before={"custom_config": {"maxTokenLifetimeDays": "90"}},
                   after={"custom_config": {"maxTokenLifetimeDays": "30"}}),
            change("databricks_permissions", ["update"], before={"authorization": "tokens", "access_control": [{"group_name": "a"}, {"group_name": "b"}]},
                   after={"authorization": "tokens", "access_control": [{"group_name": "a"}]}),
            # Grants to named groups, and deleting a setting that was not on.
            change("databricks_grants", ["update"], before={"catalog": "c", "grant": []}, after={"catalog": "c", "grant": [{"principal": "g"}]}),
            change("databricks_disable_legacy_access_setting", ["delete"], before={"disable_legacy_access": [{"value": False}]}),
        )

    def test_a_released_setting_is_not_loosened(self):
        rc = {**change("databricks_disable_legacy_access_setting", ["delete"], before={"disable_legacy_access": [{"value": True}]}),
              "address": "module.workspace_settings.databricks_disable_legacy_access_setting.this[0]"}
        code, out = run(rc, released=["module.workspace_settings.databricks_disable_legacy_access_setting.this"])
        self.assertEqual(code, 0, out)
        self.assertIn("RELEASE", out)


class Releases(unittest.TestCase):
    """A control newly left unmanaged is released (removed from the state), not destroyed."""

    def at(self, rc, addr):
        return {**rc, "address": addr}

    def test_released_deletes_are_not_risky(self):
        users = self.at(change("databricks_entitlements", ["delete"]), "module.personas.databricks_entitlements.users[0]")
        conf = self.at(change("databricks_workspace_conf", ["delete"]),
                       'module.workspace_settings.databricks_workspace_conf.key["enableTokensConfig"]')
        policy = self.at(change("databricks_budget_policy", ["delete"]), 'module.budget_policies[0].databricks_budget_policy.this["self_service"]')
        code, out = run(users, conf, policy, released=[
            "module.personas.databricks_entitlements.users",
            'module.workspace_settings.databricks_workspace_conf.key["enableTokensConfig"]',
            "module.budget_policies"])
        self.assertEqual(code, 0, out)
        for a in (users, conf, policy):
            self.assertIn("RELEASE " + a["address"], out)

    def test_other_deletes_are_still_flagged(self):
        folder = self.at(change("databricks_directory", ["delete"]), 'module.folders.databricks_directory.team["a"]')
        # A prefix must match a whole address part: .users must not release .users_extra.
        near = self.at(change("databricks_entitlements", ["delete"]), "module.personas.databricks_entitlements.users_extra[0]")
        code, out = run(folder, near, released=["module.personas.databricks_entitlements.users"])
        self.assertEqual(code, 2)
        self.assertNotIn("RELEASE", out)

    def test_a_replace_is_not_a_release(self):
        rc = self.at(change("databricks_entitlements", ["delete", "create"]), "module.personas.databricks_entitlements.users[0]")
        code, out = run(rc, released=["module.personas.databricks_entitlements.users"])
        self.assertEqual(code, 2)
        self.assertIn("REPLACE", out)


if __name__ == "__main__":
    unittest.main()
