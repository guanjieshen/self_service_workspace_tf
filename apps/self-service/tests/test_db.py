"""db/: the self-service database's migrations, grants and the rules they enforce.

The first tests need nothing. The rest run against a real Postgres when PG_TEST_DSN is set
(CI's Database tests job starts one, with no password: "host=localhost port=5432 user=postgres
dbname=postgres"); without it they are skipped and say so.
"""
import os
import pathlib
import sys
import unittest
import uuid

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / "db"))
sys.path.insert(0, str(APP))
import migrate  # noqa: E402
import store  # noqa: E402

DSN = os.environ.get("PG_TEST_DSN")


class Files(unittest.TestCase):
    def test_migrations_are_numbered_and_in_order(self):
        names = [f.name for f in migrate.migrations()]
        self.assertEqual(names, sorted(names))
        self.assertEqual(names[0], "001_requests.sql")

    def test_a_migration_that_removes_data_or_objects_says_so(self):
        """DROP, TRUNCATE, DELETE and ALTER ... DROP lose data or break the apps' queries. A
        migration may only have them with a line saying why: -- destructive: <why>."""
        import re
        risky = re.compile(r"\b(DROP|TRUNCATE|DELETE)\b", re.I)
        reviewed = {"003_run_outcome_from_jobs.sql"}   # ran before this rule (a migration that ran is never edited)
        for f in migrate.migrations():
            if f.name in reviewed:
                continue
            sql = "\n".join(l.split("--", 1)[0] for l in f.read_text().splitlines())   # statements, not comments
            with self.subTest(migration=f.name):
                if risky.search(sql):
                    self.assertRegex(f.read_text(), r"(?m)^-- destructive: \S", "add a line: -- destructive: <why it is safe>")

    def test_grants_skip_a_role_that_is_not_there_yet(self):
        only_app = migrate.grant_statements({"self_service": "app-sp"})
        self.assertTrue(only_app)
        self.assertTrue(all(set(names) == {"self_service"} for _, names in only_app))
        both = migrate.grant_statements({"self_service": "app-sp", "approvals": "approvals-sp"})
        self.assertGreater(len(both), len(only_app))

    def test_each_reader_may_only_read(self):
        lines = [(s, names) for s, names in migrate.grant_statements({"readers": "ana@contoso.com,bo@contoso.com"})]
        self.assertEqual(sorted({names["readers"] for _, names in lines}), ["ana@contoso.com", "bo@contoso.com"])
        self.assertTrue(all("INSERT" not in s.upper() for s, _ in lines), "readers read; they never write")
        self.assertEqual(migrate.grant_statements({"readers": ""}), [], "no readers, no reader grants")

    def test_nobody_is_granted_update_or_delete(self):
        statements = " ".join(s for s, _ in migrate.grant_statements({"self_service": "a", "approvals": "b"})).upper()
        self.assertNotIn("UPDATE", statements)
        self.assertNotIn("DELETE", statements)

    def test_the_business_unit_choices_are_append_only_for_the_app(self):
        statements = [s for s, _ in migrate.grant_statements({"self_service": "a", "approvals": "b"})]
        self.assertIn("GRANT SELECT, INSERT ON self_service.business_unit_choices TO {self_service};", statements)
        self.assertFalse([s for s in statements if "business_unit_choices" in s and "{approvals}" in s], "the approvals app never records one")

    def test_unknown_roles_are_refused(self):
        with self.assertRaises(SystemExit):
            migrate.main(["--dsn", "x", "--grant", "admin=someone"])


@unittest.skipUnless(DSN, "PG_TEST_DSN is not set: no Postgres to test against")
class AgainstPostgres(unittest.TestCase):
    """The rules the database itself enforces, as the apps' roles meet them."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.role = f"app_{uuid.uuid4().hex[:8]}"
        cls.reader = f"reader_{uuid.uuid4().hex[:8]}@contoso.com"
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("DROP SCHEMA IF EXISTS self_service CASCADE")
            c.execute(f'CREATE ROLE "{cls.role}"')
            c.execute(f'CREATE ROLE "{cls.reader}"')
        with psycopg.connect(DSN) as c:
            cls.first = migrate.run(c, {"self_service": cls.role, "readers": cls.reader})
        with psycopg.connect(DSN) as c:
            cls.second = migrate.run(c, {"self_service": cls.role, "readers": cls.reader})

    def as_app(self):
        c = self.psycopg.connect(DSN)
        c.execute(f'SET ROLE "{self.role}"')
        return c

    def request(self, c, rid):
        c.execute("INSERT INTO self_service.requests (id, kind, workspace, bu, requested_by, name, reason) "
                  "VALUES (%s, 'project_schema', 'fin', 'FIN', 'ana@contoso.com', 'gtm_forecast', 'Forecasting.')", (rid,))
        c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES (%s, 'ana@contoso.com', 'requester', 'submitted')", (rid,))

    def test_migrations_run_once(self):
        self.assertEqual(self.first, ["001_requests.sql", "002_one_finish_per_request.sql", "003_run_outcome_from_jobs.sql",
                                      "004_settings.sql"])
        self.assertEqual(self.second, [], "running again changes nothing")

    def test_the_app_adds_and_reads_but_never_rewrites_history(self):
        with self.as_app() as c:
            self.request(c, "ss-a1")
            c.commit()
            self.assertEqual(c.execute("SELECT state FROM self_service.request_status WHERE id = 'ss-a1'").fetchone()[0], "submitted")
            for statement in ("UPDATE self_service.requests SET reason = 'x'", "DELETE FROM self_service.request_events",
                              "UPDATE self_service.request_events SET body = 'x'", "DELETE FROM self_service.requests"):
                with self.subTest(statement=statement), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    c.execute(statement)
                c.rollback()
                c.execute(f'SET ROLE "{self.role}"')

    def test_the_first_decision_wins(self):
        with self.as_app() as c:
            self.request(c, "ss-a2")
            c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES ('ss-a2', 'dana@contoso.com', 'approver', 'approved')")
            c.commit()
            with self.assertRaises(self.psycopg.errors.UniqueViolation):
                c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES ('ss-a2', 'mo@contoso.com', 'approver', 'rejected')")
            c.rollback()

    def test_status_follows_the_events_and_ignores_comments(self):
        with self.as_app() as c:
            c.execute(f'SET ROLE "{self.role}"')
            self.request(c, "ss-a3")
            for t in ("needs_info", "commented"):
                c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES ('ss-a3', 'dana@contoso.com', 'approver', %s)", (t,))
            c.commit()
            self.assertEqual(c.execute("SELECT state FROM self_service.request_status WHERE id = 'ss-a3'").fetchone()[0], "needs_info")

    def test_a_reader_reads_and_changes_nothing(self):
        with self.psycopg.connect(DSN) as c:
            c.execute(f'SET ROLE "{self.reader}"')
            c.execute("SELECT count(*) FROM self_service.request_status").fetchone()
            for statement in ("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES ('x', 'a', 'system', 'commented')",
                              "UPDATE self_service.requests SET reason = 'x'", "DELETE FROM self_service.requests"):
                with self.subTest(statement=statement), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    c.execute(statement)
                c.rollback()
                c.execute(f'SET ROLE "{self.reader}"')

    def test_the_apps_store_round_trip_as_the_apps_role(self):
        """store.Store, with only the app's grants: record, link the run, finish (twice), read back."""
        def connect(token):
            c = self.psycopg.connect(DSN)
            c.execute(f'SET ROLE "{self.role}"')
            return c
        db = store.Store({"host": "unused", "name": "unused", "endpoint": "unused"}, credential=lambda: "t", connect=connect)
        db.record_request({"id": "ss-s1", "kind": "folder", "workspace": "fin", "bu": "FIN", "requested_by": "ana@contoso.com",
                           "name": "fin-docs", "owner_group": "fin-data-eng", "reason": "Month-end close notebooks."},
)
        db.run_started("ss-s1", "fin", 42)
        db.run_started("ss-s1", "fin", 42)          # seen again: already recorded, not an error
        db.record_request({"id": "ss-s2", "kind": "folder", "workspace": "fin", "bu": "FIN", "requested_by": "ana@contoso.com",
                           "name": "fin-other", "reason": "Notebooks for the AP team."})
        db.start_failed("ss-s2", "The job could not be started.")
        rows = {r["id"]: r for r in db.requests_of("ana@contoso.com")}
        self.assertEqual((rows["ss-s1"]["state"], rows["ss-s1"]["run_id"], rows["ss-s1"]["owner_group"]), ("run_started", 42, "fin-data-eng"))
        self.assertEqual((rows["ss-s2"]["state"], rows["ss-s2"]["state_body"]), ("start_failed", "The job could not be started."))
        self.assertEqual(db.requests_of("bo@contoso.com"), [], "only the person's own")
        with self.psycopg.connect(DSN) as c:
            types = [r[0] for r in c.execute("SELECT type FROM self_service.request_events WHERE request_id = 'ss-s1' ORDER BY id")]
        self.assertEqual(types, ["submitted", "run_started"])
        with self.as_app() as c, self.assertRaises(self.psycopg.errors.CheckViolation):
            c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type) VALUES ('ss-s1', 'a', 'system', 'run_finished')")

    def test_the_approvals_reads_as_an_approvals_role(self):
        """store.requests_in and events_of, with only the approvals app's grants."""
        approver = f"approvals_{uuid.uuid4().hex[:8]}"
        with self.psycopg.connect(DSN, autocommit=True) as c:
            c.execute(f'CREATE ROLE "{approver}"')
        with self.psycopg.connect(DSN) as c:
            migrate.run(c, {"self_service": self.role, "approvals": approver, "readers": self.reader})
        def connect(token, role=approver):
            c = self.psycopg.connect(DSN)
            c.execute(f'SET ROLE "{role}"')
            return c
        app = store.Store({"host": "-", "name": "-", "endpoint": "-"}, credential=lambda: "t", connect=lambda token: connect(token, self.role))
        app.record_request({"id": "ss-ap1", "kind": "team_schema", "workspace": "fin", "bu": "OPS", "requested_by": "ana@contoso.com",
                            "name": "ops_kpis", "owner_group": "ops-team", "reason": "KPIs for the ops team."},
)
        approvals = store.Store({"host": "-", "name": "-", "endpoint": "-"}, credential=lambda: "t", connect=connect)
        (row,) = [r for r in approvals.requests_in(["OPS"]) if r["id"] == "ss-ap1"]
        self.assertEqual((row["state"], row["run"]), ("submitted", {}))
        self.assertEqual(approvals.requests_in(["NOT-A-BU"]), [], "only the business units asked for")
        self.assertEqual([e["type"] for e in approvals.events_of("ss-ap1")], ["submitted"])
        approvals.event("ss-ap1", "commented", actor="dana@contoso.com", role="approver", body="Which KPIs?")
        self.assertTrue(approvals.decide("ss-ap1", "dana@contoso.com", "needs_info", "Which KPIs?"))
        self.assertTrue(approvals.decide("ss-ap1", "dana@contoso.com", "approved"))
        self.assertFalse(approvals.decide("ss-ap1", "mo@contoso.com", "rejected", "No."), "the first decision wins")
        (row,) = [r for r in approvals.requests_in(["OPS"]) if r["id"] == "ss-ap1"]
        self.assertEqual((row["state"], row["decision"]["outcome"], row["decision"]["by"]), ("approved", "approved", "dana@contoso.com"))
        with connect(None) as c, self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE self_service.requests SET reason = 'x'")
        # Settings: the approvals app changes them, the self-service app only reads them.
        approvals.set_settings([("faq.data", "https://wiki.example.com/faq"), ("faq.data", None)], "dana@contoso.com")
        self.assertEqual(app.settings()["faq.data"]["value"], None, "the latest change wins: back to app.yaml's")
        self.assertEqual([h["value"] for h in approvals.setting_history()[:2]], [None, "https://wiki.example.com/faq"])
        latest = approvals.setting_history(q="wiki.example")[0]
        self.assertEqual((latest["value"], latest["previous"], latest["first"]), (None, "https://wiki.example.com/faq", False))
        self.assertEqual(approvals.setting_history(keys=["banner.text"]), [], "only the settings asked for")
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            app.set_settings([("faq.data", "https://evil.example.com")], "ana@contoso.com")
        with connect(None) as c, self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE self_service.setting_events SET value = 'x'")

    def test_only_known_kinds_and_event_types(self):
        with self.as_app() as c:
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                c.execute("INSERT INTO self_service.requests (id, kind, workspace, bu, requested_by, name) VALUES ('ss-a4', 'cluster', 'w', 'B', 'a@b.c', 'n')")
            c.rollback()


if __name__ == "__main__":
    unittest.main()
