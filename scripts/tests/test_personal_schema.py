"""terraform/modules/catalog/personal_schema.py: a personal, project or team schema on request.

The notebook runs top to bottom, so each test runs it with stand-ins for dbutils and spark
and checks the SQL it sends.
"""
import json
import sys
import types
import unittest

from helpers import ROOT, render_notebook

NOTEBOOK = (ROOT / "terraform/modules/catalog/personal_schema.py").read_text()
GROUPS = {"a@contoso.com": ["fin-data-eng", "fin-local"], "jane.doe@contoso.com": []}   # each user's groups
CONFIG = {"prefix": "cd_", "privileges": ["ALL_PRIVILEGES", "MANAGE"], "owner": "fin_platform_admins", "allowed_catalogs": ["fin_citizen_dev"]}



class Exit(Exception):
    """dbutils.notebook.exit: ends the run, successfully."""


class FakeSpark:
    def __init__(self, schemas):
        self.schemas, self.sql_run = schemas, []   # schemas: {name: {tag: value}}

    def sql(self, text):
        self.sql_run.append(text)
        if text.startswith("GRANT") and text.endswith("TO `fin-local`"):   # a workspace-local group
            raise RuntimeError("[PRINCIPAL_DOES_NOT_EXIST] Could not find principal with name fin-local")
        if "information_schema.schemata" in text:
            rows = [1 for s in self.schemas if f"schema_name = '{s}'" in text]
        elif "information_schema.schema_tags" in text:
            rows = [types.SimpleNamespace(tag_value=v) for s, tags in self.schemas.items() for k, v in tags.items()
                    if f"schema_name = '{s}'" in text and f"tag_name = '{k}'" in text]
        else:
            rows = []
        return types.SimpleNamespace(count=lambda: len(rows), collect=lambda: rows)


def run(params, schemas=None, config=None):
    """Run the notebook with these request parameters (catalog defaults to the allowed one);
    returns (SQL statements, the exit value)."""
    values = {"catalog": "fin_citizen_dev", **params}
    notebook = render_notebook(NOTEBOOK, {**CONFIG, **(config or {})})
    spark = FakeSpark(schemas or {})
    out = {}

    def exit_(value):
        out["value"] = value
        raise Exit

    dbutils = types.SimpleNamespace(
        widgets=types.SimpleNamespace(text=lambda name, default: None, get=lambda name: values.get(name, "")),
        notebook=types.SimpleNamespace(exit=exit_))
    users = types.SimpleNamespace(list=lambda filter, attributes: [
        types.SimpleNamespace(groups=[types.SimpleNamespace(display=g) for g in GROUPS[e]]) for e in GROUPS if f'"{e}"' in filter])
    sdk = types.ModuleType("databricks.sdk")
    sdk.WorkspaceClient = lambda: types.SimpleNamespace(users=users)
    names = ("databricks", "databricks.sdk")
    saved = {k: sys.modules.get(k) for k in names}
    sys.modules.update(dict(zip(names, (types.ModuleType("databricks"), sdk))))
    try:
        exec(compile(notebook, "personal_schema.py", "exec"), {"dbutils": dbutils, "spark": spark, "print": lambda *a: None})
    except Exit:
        pass
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    changes = [s for s in spark.sql_run if not s.startswith("SELECT")]
    return changes, json.loads(out["value"]) if "value" in out else None


class PersonalSchema(unittest.TestCase):
    def test_creates_tags_grants_and_hands_over_a_new_schema(self):
        sql, result = run({"user": "Jane.Doe@contoso.com", "request_id": "REQ-42"})
        self.assertEqual(result, {"catalog": "fin_citizen_dev", "schema": "cd_jane_doe", "kind": "personal",
                                  "user": "jane.doe@contoso.com", "owner_group": "", "reason": "", "created": True})
        self.assertEqual(sql[0], "CREATE SCHEMA IF NOT EXISTS `fin_citizen_dev`.`cd_jane_doe` "
                                 "COMMENT 'Personal schema of jane.doe@contoso.com (self-service)'")
        self.assertIn("'cd_managed_by' = 'self_service', 'cd_user' = 'jane.doe@contoso.com', 'cd_schema_kind' = 'personal', 'cd_created' = ", sql[1])
        self.assertIn("'cd_request_id' = 'REQ-42'", sql[1])
        self.assertEqual(sql[2], "GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`cd_jane_doe` TO `jane.doe@contoso.com`",
                         "SQL spells ALL_PRIVILEGES as ALL PRIVILEGES; MANAGE lets them share it")
        self.assertEqual(sql[3], "ALTER SCHEMA `fin_citizen_dev`.`cd_jane_doe` OWNER TO `fin_platform_admins`")
        self.assertEqual(len(sql), 4)

    def test_tags_come_before_the_grant_so_a_failed_run_can_be_run_again(self):
        sql, _ = run({"user": "a@contoso.com"})
        self.assertLess(next(i for i, s in enumerate(sql) if "SET TAGS" in s), next(i for i, s in enumerate(sql) if s.startswith("GRANT")))

    def test_running_again_for_the_same_user_keeps_the_created_date(self):
        sql, result = run({"user": "a@contoso.com"}, {"cd_a": {"cd_user": "a@contoso.com", "cd_created": "2026-01-01"}})
        self.assertFalse(result["created"])
        self.assertNotIn("cd_created", sql[1])

    def test_an_existing_schema_that_is_not_the_users_is_refused(self):
        for schemas in ({"cd_a": {"cd_user": "someone.else@contoso.com"}},   # another person's
                        {"cd_a": {}}):                                         # untagged, made another way
            with self.subTest(schemas=schemas), self.assertRaises(ValueError):
                run({"user": "a@contoso.com"}, schemas)
        with self.assertRaises(ValueError):
            run({"user": "a@contoso.com", "schema": "shared"}, {"shared": {}})  # asking for a shared schema

    def test_schema_and_catalog_can_be_given(self):
        sql, result = run({"user": "a@contoso.com", "schema": "team_sandbox", "catalog": "fin_citizen_dev"})
        self.assertEqual(result["schema"], "team_sandbox")
        self.assertTrue(sql[0].startswith("CREATE SCHEMA IF NOT EXISTS `fin_citizen_dev`.`team_sandbox`"))

    def test_a_project_schema_is_tagged_as_one(self):
        sql, result = run({"user": "a@contoso.com", "schema": "gtm_integrity"})
        self.assertEqual((result["schema"], result["kind"]), ("gtm_integrity", "project"))
        self.assertIn("'cd_schema_kind' = 'project'", sql[1])
        self.assertEqual([s for s in sql if s.startswith("GRANT")], ["GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`gtm_integrity` TO `a@contoso.com`"])
        _, result = run({"user": "a@contoso.com"})
        self.assertEqual(result["kind"], "personal")

    def test_the_reason_is_kept_with_the_run_and_never_reaches_sql(self):
        reason = "Forecast the pipeline'; DROP SCHEMA x; --"
        sql, result = run({"user": "a@contoso.com", "schema": "gtm_forecast", "reason": reason})
        self.assertEqual(result["reason"], reason)
        self.assertFalse(any("DROP" in s for s in sql))
        with self.assertRaisesRegex(ValueError, "at most 1000 characters"):
            run({"user": "a@contoso.com", "schema": "gtm_forecast", "reason": "x" * 1001})

    def test_a_team_schema_is_granted_to_the_user_and_their_group(self):
        sql, result = run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-data-eng"})
        self.assertEqual((result["kind"], result["owner_group"]), ("team", "fin-data-eng"))
        self.assertIn("'cd_schema_kind' = 'team'", sql[1])
        self.assertEqual(sql[-2], "ALTER SCHEMA `fin_citizen_dev`.`fin_reporting` SET TAGS ('cd_owner_group' = 'fin-data-eng')",
                         "the group is recorded once it has the schema")
        self.assertIn("COMMENT 'Team schema of fin-data-eng (self-service)'", sql[0])
        self.assertEqual([s for s in sql if s.startswith("GRANT")], [
            "GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`fin_reporting` TO `a@contoso.com`",
            "GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`fin_reporting` TO `fin-data-eng`"])

    def test_a_team_schema_needs_a_group_of_the_users_own(self):
        with self.assertRaisesRegex(ValueError, "is not in the group fin-finance"):
            run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-finance"})
        with self.assertRaisesRegex(ValueError, "personal schema is the user's alone"):
            run({"user": "a@contoso.com", "owner_group": "fin-data-eng"})
        with self.assertRaisesRegex(ValueError, "fin-local cannot be given the schema: Unity Catalog grants only to account groups"):
            run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-local"})
        with self.assertRaisesRegex(ValueError, "not a group name"):   # before it goes anywhere near SQL
            run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "x` TO `users"})

    def test_a_project_schema_cannot_take_a_personal_name(self):
        with self.assertRaisesRegex(ValueError, "may not start with cd_"):
            run({"user": "a@contoso.com", "schema": "cd_bo"})
        _, result = run({"user": "a@contoso.com", "schema": "cd_a"})   # asking for your own personal one by name is fine
        self.assertEqual(result["kind"], "personal")

    def test_no_owner_leaves_the_owner_alone(self):
        sql, _ = run({"user": "a@contoso.com"}, config={"owner": ""})
        self.assertFalse(any("OWNER TO" in s for s in sql))

    def test_bad_requests_are_refused_before_any_change(self):
        for params in ({"user": ""}, {"user": "not-an-email"}, {"user": "a`@contoso.com"},
                       {"user": "a@contoso.com", "schema": "Bad-Name"}, {"user": "a@contoso.com", "schema": "x`; DROP"},
                       {"user": "a@contoso.com", "catalog": "other_catalog"},
                       {"user": "a@contoso.com", "catalog": ""},              # the catalog is required
                       {"user": "a@contoso.com", "request_id": "x'; DROP"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                run(params)
        with self.assertRaises(ValueError):
            run({"user": "a@contoso.com"}, config={"privileges": ["ALL PRIVILEGES; DROP"]})

    def test_a_run_cannot_change_the_settings_from_catalog_yaml(self):
        # Databricks hands a run's parameters to the notebook even when the job does not
        # define them; the settings are written into the notebook, not read from widgets.
        sql, _ = run({"user": "a@contoso.com", "owner": "users", "privileges": "MANAGE", "prefix": "x_",
                      "allowed_catalogs": "other"})
        self.assertIn("OWNER TO `fin_platform_admins`", sql[-1])
        self.assertTrue(sql[0].startswith("CREATE SCHEMA IF NOT EXISTS `fin_citizen_dev`.`cd_a`"))
        self.assertIn("GRANT ALL PRIVILEGES, MANAGE ON", sql[2])


if __name__ == "__main__":
    unittest.main()
