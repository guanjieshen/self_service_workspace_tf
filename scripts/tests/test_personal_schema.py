"""bundle/jobs/notebooks/personal_schema.py: a personal, project or team schema on request.

The notebook runs top to bottom, so each test runs it with stand-ins for dbutils and spark
and checks the SQL it sends.
"""
import json
import sys
import types
import unittest

from notebook_helpers import ROOT, RecordsSpark, render_notebook

NOTEBOOK = (ROOT / "bundle/jobs/notebooks/personal_schema.py").read_text()
GROUPS = {"a@contoso.com": ["fin-data-eng", "fin-local"], "sam.lee@contoso.com": []}   # each user's groups
CONFIG = {"prefix": "cd_", "privileges": ["ALL_PRIVILEGES", "MANAGE"], "owner": "fin_platform_admins", "allowed_catalogs": ["fin_citizen_dev"],
          "comment_model": ""}
MODEL = {"comment_model": "system.ai.claude-sonnet-5-5"}



class Exit(Exception):
    """dbutils.notebook.exit: ends the run, successfully."""


class FakeSpark:
    def __init__(self, schemas, raced=(), answer="Holds the sales team's weekly forecasts."):
        self.schemas, self.sql_run, self.asked = schemas, [], []   # schemas: {name: {tag: value}}
        self.raced = set(raced)   # created by another run between this run's check and its CREATE
        self.answer = answer      # what ai_query answers; an Exception: it fails

    def sql(self, text, args=None):
        self.sql_run.append(text)
        if "ai_query" in text:
            self.asked.append(args)
            if isinstance(self.answer, Exception):
                raise self.answer
            return types.SimpleNamespace(first=lambda: types.SimpleNamespace(text=self.answer))
        if text.startswith("CREATE SCHEMA") and any(f".`{s}`" in text for s in self.raced):
            raise RuntimeError("[SCHEMA_ALREADY_EXISTS] Cannot create schema because it already exists.")
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


def run(params, schemas=None, config=None, records=None, raced=(), answer=None, asked=None):
    """Run the notebook with these request parameters (catalog defaults to the allowed one);
    returns (SQL statements, the exit value). asked, a list: gets each ai_query's parameters."""
    values = {"catalog": "fin_citizen_dev", **params}
    notebook = render_notebook(NOTEBOOK, {**CONFIG, **(config or {})})
    spark = FakeSpark(schemas or {}, raced, **({"answer": answer} if answer is not None else {}))
    spark.asked = asked if asked is not None else spark.asked
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
        reads = RecordsSpark(records or {}, spark.sql)   # the app's records, when the check is on
        exec(compile(notebook, "personal_schema.py", "exec"), {"dbutils": dbutils, "spark": reads, "print": lambda *a: None})
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
        sql, result = run({"user": "Sam.Lee@contoso.com", "request_id": "REQ-42"})
        self.assertEqual(result, {"catalog": "fin_citizen_dev", "schema": "cd_sam_lee", "kind": "personal",
                                  "user": "sam.lee@contoso.com", "owner_group": "", "reason": "", "created": True})
        self.assertEqual(sql[0], "CREATE SCHEMA `fin_citizen_dev`.`cd_sam_lee` "
                                 "COMMENT 'Personal schema of sam.lee@contoso.com (self-service)'")
        self.assertIn("'cd_managed_by' = 'self_service', 'cd_user' = 'sam.lee@contoso.com', 'cd_schema_kind' = 'personal', 'cd_created' = ", sql[1])
        self.assertIn("'cd_request_id' = 'REQ-42'", sql[1])
        self.assertEqual(sql[2], "GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`cd_sam_lee` TO `sam.lee@contoso.com`",
                         "SQL spells ALL_PRIVILEGES as ALL PRIVILEGES; MANAGE lets them share it")
        self.assertEqual(sql[3], "ALTER SCHEMA `fin_citizen_dev`.`cd_sam_lee` OWNER TO `fin_platform_admins`")
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

    def test_two_requests_for_one_new_name_never_share_it(self):
        # Both runs saw the name free; the other run created it first: this one stops, changing nothing.
        with self.assertRaisesRegex(ValueError, "just created by another request: choose another name"):
            run({"user": "a@contoso.com", "schema": "fin_forecast"}, raced={"fin_forecast"})
        sql, _ = run({"user": "a@contoso.com", "schema": "fin_forecast"}, {"fin_forecast": {"cd_user": "a@contoso.com"}})
        self.assertFalse(any(q.startswith("CREATE") for q in sql), "the user's own, run again: not created again")
        self.assertTrue(any(q.startswith("GRANT") for q in sql), "and still granted")

    def test_schema_and_catalog_can_be_given(self):
        sql, result = run({"user": "a@contoso.com", "schema": "team_sandbox", "catalog": "fin_citizen_dev"})
        self.assertEqual(result["schema"], "team_sandbox")
        self.assertTrue(sql[0].startswith("CREATE SCHEMA `fin_citizen_dev`.`team_sandbox`"))

    def test_a_project_schema_is_tagged_as_one(self):
        sql, result = run({"user": "a@contoso.com", "schema": "sales_bookings"})
        self.assertEqual((result["schema"], result["kind"]), ("sales_bookings", "project"))
        self.assertIn("'cd_schema_kind' = 'project'", sql[1])
        self.assertEqual([s for s in sql if s.startswith("GRANT")], ["GRANT ALL PRIVILEGES, MANAGE ON SCHEMA `fin_citizen_dev`.`sales_bookings` TO `a@contoso.com`"])
        _, result = run({"user": "a@contoso.com"})
        self.assertEqual(result["kind"], "personal")

    def test_the_reason_is_kept_with_the_run_and_never_sql_text(self):
        reason = "Forecast the pipeline'; DROP SCHEMA x; --"
        sql, result = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": reason})
        self.assertEqual(result["reason"], reason)
        self.assertFalse(any("DROP" in s for s in sql))
        asked = []
        sql, _ = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": reason}, config=MODEL, asked=asked, answer="Forecasts.")
        self.assertFalse(any(reason in s for s in sql), "with a model, only ai_query's parameter")
        self.assertIn(reason, asked[0]["prompt"])
        with self.assertRaisesRegex(ValueError, "at most 1000 characters"):
            run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "x" * 1001})

    def test_a_new_project_or_team_schema_says_what_it_is_for(self):
        asked = []
        sql, result = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Weekly forecasts for the sales team."},
                          config=MODEL, asked=asked)
        self.assertTrue(result["created"])
        self.assertEqual(sql[-2:], ["COMMENT ON SCHEMA `fin_citizen_dev`.`sales_forecast` IS 'Holds the sales team\\'s weekly forecasts.'",
                                    "ALTER SCHEMA `fin_citizen_dev`.`sales_forecast` OWNER TO `fin_platform_admins`"],
                         "written before the hand-over, while the job still owns it")
        self.assertEqual(asked[0]["model"], "system.ai.claude-sonnet-5-5")
        self.assertIn("project schema named sales_forecast", asked[0]["prompt"])
        self.assertTrue(asked[0]["prompt"].endswith("Weekly forecasts for the sales team."), "the reason, as a parameter")
        self.assertTrue(sql[0].endswith("COMMENT 'Project schema of a@contoso.com (self-service)'"), "the plain comment first")
        sql, _ = run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-data-eng", "reason": "Reports."}, config=MODEL)
        self.assertTrue(any(s.startswith("COMMENT ON SCHEMA `fin_citizen_dev`.`fin_reporting`") for s in sql), "a team schema too")

    def test_the_models_text_is_one_escaped_line_never_sql(self):
        sql, _ = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Forecasts."}, config=MODEL,
                     answer="\"Forecasts\\ for\n sales'; DROP SCHEMA x; --\"" + "x" * 600)
        comment = next(s for s in sql if s.startswith("COMMENT ON"))
        self.assertTrue(comment.startswith("COMMENT ON SCHEMA `fin_citizen_dev`.`sales_forecast` IS 'Forecasts\\\\ for sales\\'; DROP SCHEMA x; --"))
        self.assertNotIn("\n", comment)
        self.assertLess(len(comment), 600, "at most 500 characters of it")

    def test_without_an_answer_the_schema_keeps_its_plain_comment(self):
        sql, result = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Forecasts."}, config=MODEL,
                          answer=RuntimeError("PERMISSION_DENIED: no EXECUTE on the model"))
        self.assertTrue(result["created"], "never a reason to fail the request")
        self.assertFalse([s for s in sql if s.startswith("COMMENT ON")])
        sql, _ = run({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Forecasts."}, config=MODEL, answer="  ")
        self.assertFalse([s for s in sql if s.startswith("COMMENT ON")], "an empty answer: no comment")

    def test_only_a_new_project_or_team_schema_with_a_reason_and_a_model_is_described(self):
        for params, schemas, config, why in (
                ({"user": "sam.lee@contoso.com", "reason": "Mine."}, None, MODEL, "a personal schema"),
                ({"user": "a@contoso.com", "schema": "sales_forecast"}, None, MODEL, "no reason"),
                ({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Forecasts."}, None, None, "no model"),
                ({"user": "a@contoso.com", "schema": "sales_forecast", "reason": "Forecasts."},
                 {"sales_forecast": {"cd_user": "a@contoso.com"}}, MODEL, "run again: it has its comment")):
            with self.subTest(why):
                asked = []
                sql, result = run(params, schemas=schemas, config=config, asked=asked)
                self.assertIsNotNone(result)
                self.assertEqual(asked, [])
                self.assertFalse([s for s in sql if s.startswith("COMMENT ON")])

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

    def test_a_team_schema_takes_any_account_group(self):
        # Membership is not checked (the job runs in the hub, which does not see a person's groups).
        sql, result = run({"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-finance"})
        self.assertEqual(result["owner_group"], "fin-finance", "a group they are not in")
        self.assertTrue(any(q.startswith("GRANT") and q.endswith("TO `fin-finance`") for q in sql))
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

    def test_a_run_cannot_change_the_settings_written_in(self):
        # Databricks hands a run's parameters to the notebook even when the job does not
        # define them; the settings are written into the notebook, not read from widgets.
        sql, _ = run({"user": "a@contoso.com", "owner": "users", "privileges": "MANAGE", "prefix": "x_",
                      "allowed_catalogs": "other"})
        self.assertIn("OWNER TO `fin_platform_admins`", sql[-1])
        self.assertTrue(sql[0].startswith("CREATE SCHEMA `fin_citizen_dev`.`cd_a`"))
        self.assertIn("GRANT ALL PRIVILEGES, MANAGE ON", sql[2])



ON = {"requests_catalog": "cd_requests", "workspace_name": "fin", "human_approval": ["project_schema", "team_schema"]}
TEAM = {"user": "a@contoso.com", "schema": "fin_reporting", "owner_group": "fin-data-eng", "request_id": "ss-1"}
TEAM_RECORD = {"kind": "team_schema", "workspace": "fin", "requested_by": "a@contoso.com", "name": "fin_reporting", "owner_group": "fin-data-eng"}
MINE = {"kind": "personal_schema", "workspace": "fin", "requested_by": "a@contoso.com", "name": "cd_a", "owner_group": ""}


class RequestRecord(unittest.TestCase):
    """jobs.require_request_record: only a request the app recorded, as recorded, and approved by
    a person when its kind needs one (app.yaml human_approval)."""

    def test_off_by_default_nothing_is_read(self):
        _, result = run({"user": "a@contoso.com"})
        self.assertEqual(result["schema"], "cd_a")

    def test_a_team_schema_runs_once_an_approver_approved_it(self):
        _, result = run(TEAM, config=ON, records={"ss-1": (TEAM_RECORD, [("reviewed", None), ("approved", None)])})
        self.assertEqual(result["schema"], "fin_reporting")

    def test_a_personal_schema_needs_only_its_record(self):
        _, result = run({"user": "a@contoso.com", "request_id": "ss-2"}, config=ON, records={"ss-2": (MINE, [])})
        self.assertEqual(result["kind"], "personal")

    def test_a_kind_left_out_of_human_approval_needs_only_its_record(self):
        _, result = run(TEAM, config={**ON, "human_approval": ["project_schema"]}, records={"ss-1": (TEAM_RECORD, [])})
        self.assertEqual(result["kind"], "team")

    def test_anything_else_is_refused(self):
        approved = [("approved", None)]
        cases = [
            ("is not a request the self-service app recorded", {**TEAM, "request_id": "ss-404"}, {}),
            ("request_id is required", {**TEAM, "request_id": ""}, {}),
            ("requested_by differ", {"user": "bo@contoso.com", "request_id": "ss-2"}, {"ss-2": ({**MINE, "name": "cd_bo"}, [])}),
            ("name differ", {**TEAM, "schema": "fin_other"}, {"ss-1": (TEAM_RECORD, approved)}),
            ("workspace differ", TEAM, {"ss-1": ({**TEAM_RECORD, "workspace": "sales"}, approved)}),
            ("always needs a person", TEAM, {"ss-1": (TEAM_RECORD, [("reviewed", None)])}),              # waiting
            ("always needs a person", TEAM, {"ss-1": (TEAM_RECORD, [("rejected", None)])}),              # rejected
        ]
        for message, params, records in cases:
            with self.subTest(message=message, records=records), self.assertRaisesRegex(ValueError, message):
                run(params, config=ON, records=records)

if __name__ == "__main__":
    unittest.main()
