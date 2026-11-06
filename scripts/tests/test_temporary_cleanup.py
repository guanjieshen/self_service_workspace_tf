"""bundle/jobs/notebooks/temporary_cleanup.py: drops expired temporary schemas, once a day.

The notebook runs top to bottom, so each test runs it with stand-ins for dbutils and spark on a
fake catalog, and checks what it dropped and what it reported.
"""
import datetime as dt
import json
import types
import unittest

from notebook_helpers import ROOT, render_notebook

NOTEBOOK = (ROOT / "bundle/jobs/notebooks/temporary_cleanup.py").read_text()
TODAY = dt.date.today()
DAY = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()


def temporary(user="ana@contoso.com", expires=DAY(-1), **tags):
    return {"cd_managed_by": "self_service", "cd_schema_kind": "temporary", "cd_user": user, "cd_created": DAY(-31),
            "cd_expires": expires, **tags}


class Exit(Exception):
    """dbutils.notebook.exit: ends the run, successfully."""


class FakeSpark:
    def __init__(self, schemas, tables=None, fail=()):
        self.schemas, self.tables, self.fail, self.sql_run = schemas, tables or {}, set(fail), []

    def sql(self, text):
        self.sql_run.append(text)
        if text.startswith("DROP SCHEMA"):
            name = text.split("`.`", 1)[1].split("`", 1)[0]
            if name in self.fail:
                raise RuntimeError("[PERMISSION_DENIED] User does not have MANAGE on Schema\nmore detail")
            self.schemas.pop(name)
            rows = []
        elif "information_schema.schema_tags" in text:
            rows = [types.SimpleNamespace(schema_name=s, tag_name=k, tag_value=v) for s, tags in self.schemas.items()
                    for k, v in tags.items() if f"'{k}'" in text]
        elif "information_schema.tables" in text:
            n = next((n for s, n in self.tables.items() if f"table_schema = '{s}'" in text), 0)
            rows = [types.SimpleNamespace(n=n)]
        else:
            rows = []
        return types.SimpleNamespace(collect=lambda: rows, first=lambda: rows[0])

    def createDataFrame(self, rows):
        return rows


def run(schemas, dry_run="", **kw):
    """Run the notebook; returns (the fake spark, the report it exited with or set, the error if it failed)."""
    spark = FakeSpark(schemas, **kw)
    out = {}

    def exit_(value):
        out["exit"] = value
        raise Exit

    dbutils = types.SimpleNamespace(
        widgets=types.SimpleNamespace(text=lambda name, default: None, get=lambda name: dry_run),
        jobs=types.SimpleNamespace(taskValues=types.SimpleNamespace(set=lambda key, value: out.__setitem__(key, value))),
        notebook=types.SimpleNamespace(exit=exit_))
    notebook = render_notebook(NOTEBOOK, {"prefix": "cd_", "allowed_catalogs": ["fin_citizen_dev"]})
    error = None
    try:
        exec(compile(notebook, "temporary_cleanup.py", "exec"),
             {"dbutils": dbutils, "spark": spark, "display": lambda df: None, "print": lambda *a, **k: None})
    except Exit:
        pass
    except RuntimeError as e:
        error = e
    return spark, json.loads(out["report"]), error


class Cleanup(unittest.TestCase):
    def test_drops_expired_temporary_schemas_and_keeps_the_rest(self):
        spark, report, error = run({"cd_tmp_old": temporary(), "cd_tmp_live": temporary(expires=DAY(3)),
                                    "cd_tmp_today": temporary(expires=DAY(0))}, tables={"cd_tmp_old": 4})
        self.assertIsNone(error)
        self.assertEqual([s for s in spark.sql_run if s.startswith("DROP")], ["DROP SCHEMA `fin_citizen_dev`.`cd_tmp_old` CASCADE"])
        rows = {r["schema"]: r for r in report["schemas"]}
        self.assertEqual((rows["cd_tmp_old"]["action"], rows["cd_tmp_old"]["tables"], rows["cd_tmp_old"]["user"], rows["cd_tmp_old"]["created"]),
                         ("dropped", 4, "ana@contoso.com", DAY(-31)), "what was dropped: whose, when made, how many tables")
        self.assertEqual((rows["cd_tmp_live"]["action"], rows["cd_tmp_live"]["why"]), ("kept", f"expires on {DAY(3)}"))
        self.assertEqual(rows["cd_tmp_today"]["action"], "kept", "it is still theirs on its expiry date (as the app counts it)")
        self.assertEqual((report["date"], report["counts"]), (TODAY.isoformat(), {"dropped": 1, "would drop": 0, "kept": 2, "failed": 0}))

    def test_never_touches_a_schema_it_did_not_make_as_temporary(self):
        spark, report, _ = run({"cd_ana": {"cd_managed_by": "self_service", "cd_schema_kind": "personal", "cd_expires": DAY(-9)},
                                "cd_tmp_theirs": {"cd_schema_kind": "temporary", "cd_expires": DAY(-9)},   # not the job's
                                "sales": {"cd_expires": DAY(-9)}})
        self.assertFalse([s for s in spark.sql_run if s.startswith("DROP")])
        self.assertEqual(report["schemas"], [], "not reported either: not a temporary schema of the app's")

    def test_a_temporary_schema_without_its_name_or_date_is_kept_and_said_why(self):
        spark, report, _ = run({"other_name": temporary(), "cd_tmp_nodate": temporary(expires="soon")})
        self.assertFalse([s for s in spark.sql_run if s.startswith("DROP")])
        self.assertEqual({r["schema"]: r["why"] for r in report["schemas"]},
                         {"other_name": "not named cd_tmp_<name>", "cd_tmp_nodate": "no valid cd_expires date"})

    def test_a_dry_run_drops_nothing_and_says_what_it_would(self):
        spark, report, _ = run({"cd_tmp_old": temporary()}, dry_run="true")
        self.assertFalse([s for s in spark.sql_run if s.startswith("DROP")])
        self.assertEqual((report["dry_run"], report["schemas"][0]["action"]), (True, "would drop"))

    def test_a_schema_that_cannot_be_dropped_is_reported_and_fails_the_run_after_the_others(self):
        spark, report, error = run({"cd_tmp_a": temporary(), "cd_tmp_b": temporary()}, fail={"cd_tmp_a"})
        self.assertIn("1 temporary schema(s) could not be dropped", str(error))
        rows = {r["schema"]: r for r in report["schemas"]}
        self.assertEqual((rows["cd_tmp_a"]["action"], rows["cd_tmp_a"]["why"]), ("failed", "[PERMISSION_DENIED] User does not have MANAGE on Schema"))
        self.assertEqual(rows["cd_tmp_b"]["action"], "dropped", "one failure never stops the others")

    def test_nothing_to_do_is_a_quiet_success(self):
        _, report, error = run({})
        self.assertIsNone(error)
        self.assertEqual(report["schemas"], [])


class Summary(unittest.TestCase):
    def test_it_says_how_many_were_deleted_whose_and_how_many_tables(self):
        spark, report, _ = run({"cd_tmp_old": temporary(), "cd_tmp_bo": temporary(user="bo@contoso.com"),
                                "cd_tmp_live": temporary(expires=DAY(3))}, tables={"cd_tmp_old": 4, "cd_tmp_bo": 1})
        self.assertEqual(report["summary"], "\n".join([
            f"Temporary schema cleanup on {TODAY.isoformat()}: deleted 2 schemas, with 5 tables.",
            "  bo@contoso.com: fin_citizen_dev.cd_tmp_bo (1 table)",
            "  ana@contoso.com: fin_citizen_dev.cd_tmp_old (4 tables)",
            "Kept 1 temporary schema that has not expired."]))
        self.assertFalse([s for s in spark.sql_run if "ai_" in s], "exact numbers and emails: written from the report, no model")

    def test_a_dry_run_says_what_it_would_delete(self):
        _, report, _ = run({"cd_tmp_old": temporary()}, dry_run="true")
        self.assertTrue(report["summary"].startswith(f"Temporary schema cleanup on {TODAY.isoformat()} (dry run): would delete 1 schema, with 0 tables."))

    def test_a_failure_is_in_the_summary_with_its_reason(self):
        _, report, error = run({"cd_tmp_a": temporary()}, fail={"cd_tmp_a"})
        self.assertIsNotNone(error)
        self.assertIn("deleted 0 schemas, with 0 tables.", report["summary"])
        self.assertIn("Could not delete 1 schema:\n  ana@contoso.com: fin_citizen_dev.cd_tmp_a: [PERMISSION_DENIED]", report["summary"])

    def test_nothing_to_do(self):
        _, report, _ = run({})
        self.assertEqual(report["summary"], f"Temporary schema cleanup on {TODAY.isoformat()}: deleted 0 schemas, with 0 tables.\n"
                                            "Kept 0 temporary schemas that have not expired.")


if __name__ == "__main__":
    unittest.main()
