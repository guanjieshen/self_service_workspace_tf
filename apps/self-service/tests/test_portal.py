"""portal.py and main.py: the self-service app, with a fake Databricks client.

The page tests need the app's requirements (requirements.txt) and httpx. Run on their own
they are skipped without them; ./scripts/test.sh app (and CI) fails instead.
"""
import io
import json
import pathlib
import sys
import types
import unittest
from unittest import mock

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
sys.path.insert(0, str(APP))
import portal  # noqa: E402
from databricks.sdk.errors import NotFound  # noqa: E402

HOST = "https://adb-1.azuredatabricks.net"
HUB = "https://adb-9.azuredatabricks.net"
CONFIG = {"title": "Citizen Development", "hub_host": HUB, "links": {}, "ai": {"model": "system.ai.claude-sonnet-5-5"}, "workspaces": [
    {"name": "fin", "bu": "FIN", "host": HOST}, {"name": "down", "bu": "OPS", "host": "https://down"}]}
ANA, BO = "ana@contoso.com", "bo@contoso.com"
WHY = "Monthly reconciliation reports for the team."   # every named schema and folder needs a reason


def ns(**kw):
    return types.SimpleNamespace(**kw)


def state(life, result=None, message=""):
    return ns(life_cycle_state=ns(value=life), result_state=ns(value=result) if result else None, state_message=message)


def run_of(run_id, job_id, params, life="TERMINATED", result="SUCCESS", output=None, error=None):
    return ns(run_id=run_id, job_id=job_id, start_time=1_700_000_000_000 + run_id,
              job_parameters=[ns(name=k, value=v, default="") for k, v in params.items()],
              state=state(life, result), tasks=[ns(run_id=run_id * 10)], output=output, error=error)


class FakeClient:
    """The hub: the jobs (tagged as the bundle tags them), runs, schemas and the AI gateway the app uses."""

    def __init__(self):
        # In the hub, each tagged with the workspace it serves (scripts/app_build.py jobs_target).
        self.jobs_ = [ns(job_id=1, settings=ns(tags={"cd_self_service": "personal_schema", "cd_catalog": "fin_citizen_dev", "cd_prefix": "cd_",
                                                    "cd_workspace": "fin"})),
                      ns(job_id=2, settings=ns(tags={"cd_self_service": "team_folder", "cd_root": "/Workspace", "cd_workspace": "fin"})),
                      ns(job_id=3, settings=ns(tags={}))]
        self.runs_ = {}
        self.started, self.get_runs = [], 0
        self.jobs = ns(list=lambda: self.jobs_, run_now=self.run_now, get_run=self.get_run,
                       list_runs=self.list_runs,
                       get_run_output=lambda task_run_id: next(
                           ns(error=r.error, notebook_output=ns(result=r.output)) for r in self.runs_.values() if r.run_id * 10 == task_run_id))
        self.users = ns(list=lambda filter, attributes, count=None: [
            ns(user_name=ANA, groups=[ns(display="fin-data-eng"), ns(display="fin_builder")])] if ANA in filter or "sw" in filter else [])
        self.groups = ns(list=lambda filter, attributes, count=None: [ns(display_name="fin-data-eng")])
        self.schemas_ = set()          # schemas the app can see (BROWSE); None = it cannot see any
        self.schemas = ns(get=self.get_schema)
        self.folders_ = {}             # path -> "mine" or "theirs" (the app sees theirs as permission denied)
        self.workspace = ns(get_status=self.get_status)
        # The AI gateway, for the Validate check: the answer to each question (None = it cannot be
        # reached), and what was asked.
        self.decide, self.decided = dict(portal.checks.SAFE), []
        self.api_client = ns(do=self.api)
        # The BU lookup (SQL statements): person -> business unit; None = the warehouse cannot answer.
        self.bus_, self.statements = {ANA: "FIN"}, []

    def api(self, method, path, body=None):
        if path == "/api/2.0/sql/statements":
            self.statements.append(body)
            if self.bus_ is None:
                raise ConnectionError("warehouse unreachable")
            return {"status": {"state": "SUCCEEDED"}, "result": {"data_array": [[self.bus_.get(body["parameters"][0]["value"])]]}}
        return self.ai_gateway(method, path, body)

    def ai_gateway(self, method, path, body=None):
        assert path == portal.checks.API, path
        if self.decide is None:
            raise ConnectionError("the AI gateway is not reachable")
        self.decided.append(body)
        return {"choices": [{"message": {"content": "Sure: " + json.dumps(self.decide)}}]}

    def get_status(self, path):
        from databricks.sdk.errors import PermissionDenied
        if path not in self.folders_:
            raise NotFound(f"Path ({path}) doesn't exist.")
        if self.folders_[path] == "theirs":
            raise PermissionDenied("This user does not have permission")
        return ns(object_id=1)

    def get_schema(self, full_name):
        if self.schemas_ is None:
            raise PermissionError("User does not have USE CATALOG on Catalog")
        if full_name not in self.schemas_:
            raise NotFound(f"Schema '{full_name}' does not exist.")
        return ns(full_name=full_name)

    def list_runs(self, job_id, limit=None, expand_tasks=None, active_only=None):
        return [r for r in self.runs_.values() if r.job_id == job_id
                and (not active_only or r.state.life_cycle_state.value not in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"))]

    def run_now(self, job_id, job_parameters):
        run_id = 100 + len(self.started)
        self.started.append((job_id, job_parameters))
        self.runs_[run_id] = run_of(run_id, job_id, job_parameters, life="QUEUED", result=None)
        return ns(run_id=run_id)

    def get_run(self, run_id):
        self.get_runs += 1
        if run_id not in self.runs_:
            raise NotFound(f"Run {run_id} does not exist.")
        return self.runs_[run_id]


def make(store=None):
    """A portal on the fake client, and its requests database (FakeStore unless given)."""
    fake = FakeClient()

    def client(host):
        if host not in (HOST, None):   # None: the app's own workspace (the hub)
            raise ConnectionError("no route to host\nmore detail")
        return fake
    return portal.Portal(CONFIG, client, store=FakeStore() if store is None else store), fake


class FakeStore:
    """The app's database, in memory: the same methods as store.Store, and the same rules (a
    run starts and ends once per request; history is only added to)."""

    def __init__(self):
        self.requests, self.events, self.fail = {}, [], None   # fail: "write" or "read"

    def ping(self):
        return True

    def record_request(self, r):
        if self.fail == "write":
            raise ConnectionError("database unreachable")
        self.requests[r["id"]] = dict(r, created_at=__import__("datetime").datetime(2026, 10, 21, 12, len(self.requests)))
        self.events.append((r["id"], "submitted", {}))

    def event(self, request_id, type_, data=None, actor=None, role=None, body=None):
        if any(e[0] == request_id and e[1] == type_ for e in self.events) and type_ == "run_started":
            return   # ON CONFLICT DO NOTHING
        self.events.append((request_id, type_, {**(data or {}), **({"actor": actor} if actor else {}), **({"body": body} if body else {})}))

    def events_of(self, request_id):
        at = __import__("datetime").datetime(2026, 10, 21, 12, 0)
        who = lambda rid, t: self.requests[rid]["requested_by"] if t == "submitted" else "Citizen Development app"
        return [{"at": at, "actor": d.get("actor", who(rid, t)), "role": "approver" if t in ("needs_info", "approved", "rejected") else "system",
                 "type": t, "body": d.get("body"), "data": d} for rid, t, d in self.events if rid == request_id]

    def summarized(self, request_id, summary, actor="AI summary"):
        self.events.append((request_id, "reviewed", {"summary": summary}))

    def run_started(self, request_id, workspace, run_id):
        self.event(request_id, "run_started", {"workspace": workspace, "run_id": int(run_id)})

    def start_failed(self, request_id, message):
        self.events.append((request_id, "start_failed", {"body": message}))

    def chosen_business_unit(self, email):
        return getattr(self, "chosen", {}).get(email.lower())

    def choose_business_unit(self, email, bu):
        self.chosen = {**getattr(self, "chosen", {}), email.lower(): bu.upper()}

    def toured(self, email):
        return email.lower() in getattr(self, "tours", [])

    def record_tour(self, email):
        self.tours = [*getattr(self, "tours", []), email.lower()]

    def requests_of(self, user, limit=200):
        if self.fail == "read":
            raise ConnectionError("database unreachable")
        out = []
        for rid, r in self.requests.items():
            if r["requested_by"] != user:
                continue
            mine = [e for e in self.events if e[0] == rid and e[1] not in ("reviewed", "commented")]
            state, data = mine[-1][1], mine[-1][2]
            run = next((e[2] for e in self.events if e[0] == rid and e[1] == "run_started"), {})
            out.append({**r, "state": state, "state_data": data, "state_body": data.get("body"), "run_id": run.get("run_id")})
        return sorted(out, key=lambda r: r["created_at"], reverse=True)[:limit]


class Discovery(unittest.TestCase):
    def test_finds_each_workspaces_job_in_the_hub_by_its_tag(self):
        # Every workspace's job is in the hub, tagged with the workspace it serves: one listing,
        # no call to another workspace (the fake raises for any host but the hub's).
        p, _ = make()
        fin, down = p.workspaces()
        self.assertEqual({k: j["id"] for k, j in fin.jobs.items()}, {"personal_schema": 1, "team_folder": 2})
        self.assertEqual(fin.error, "")
        self.assertEqual((fin.host, down.host), (HOST, "https://down"), "each keeps its own address, for the links people open")
        self.assertEqual(down.jobs, {})
        self.assertIn("no Citizen Development job found in the hub", down.error)

    def test_a_hub_that_cannot_be_read_is_said_for_every_workspace(self):
        p, fake = make()
        fake.jobs.list = lambda: (_ for _ in ()).throw(ConnectionError("hub down"))
        self.assertTrue(all("the hub's jobs cannot be read: hub down" in w.error for w in p.workspaces()))


class Submitting(unittest.TestCase):
    def test_schema_runs_the_job_with_the_user_and_the_workspace_catalog(self):
        p, fake = make()
        run_id = p.request_schema("fin", ANA)
        job_id, params = fake.started[0]
        self.assertEqual((run_id, job_id), (100, 1))
        self.assertEqual((params["user"], params["catalog"]), (ANA, "fin_citizen_dev"))
        self.assertRegex(params["request_id"], r"^ss-[0-9a-f]{8}$")

    def test_folder_runs_the_job_with_the_permissions(self):
        p, fake = make()
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        job_id, params = fake.started[0]
        self.assertEqual((job_id, params["folder"], params["requested_by"]), (2, "fin-docs", ANA))
        self.assertEqual(params["owner_group"], "", "no owner group: the job gives the platform admins Can manage")

    def test_bad_requests_are_refused_before_any_run(self):
        p, fake = make()
        for folder in ("Fin Docs", "users", 'x" or "1'):
            with self.subTest(folder=folder), self.assertRaises(portal.RequestError):
                p.request_folder("fin", ANA, folder, reason=WHY)
        with self.assertRaises(portal.RequestError):
            p.request_schema("down", ANA)            # a workspace without the job
        with self.assertRaises(portal.RequestError):
            p.request_schema("fin", "not-an-email")
        self.assertEqual(fake.started, [])


class Status(unittest.TestCase):
    def test_phases_follow_the_run(self):
        p, fake = make()
        run_id = p.request_schema("fin", ANA)
        self.assertEqual((p.run("fin", run_id, ANA).status, p.run("fin", run_id, ANA).phase), ("In progress", "Starting"))
        p.run_cache_seconds = 0
        fake.runs_[run_id].state = state("RUNNING")
        self.assertEqual(p.run("fin", run_id, ANA).phase, "Running")
        fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        r = p.run("fin", run_id, ANA)
        self.assertEqual((r.status, r.resource, r.link), ("Completed", "fin_citizen_dev.cd_ana", f"{HOST}/explore/data/fin_citizen_dev/cd_ana"))

    def test_a_failed_run_says_why_in_the_jobs_words(self):
        p, fake = make()
        run_id = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        fake.runs_[run_id].state = state("TERMINATED", "FAILED", "Workload failed")
        fake.runs_[run_id].error = "ValueError: /Workspace/fin-docs already exists and is not managed by ana@contoso.com\nTraceback..."
        r = p.run("fin", run_id, ANA)
        self.assertEqual((r.status, r.message), ("Failed", "/Workspace/fin-docs already exists and is not managed by ana@contoso.com"))

    def test_a_completed_folder_links_to_it(self):
        p, fake = make()
        run_id = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        fake.runs_[run_id].output = json.dumps({"path": "/Workspace/fin-docs", "object_id": 77})
        self.assertEqual(p.run("fin", run_id, ANA).link, f"{HOST}/browse/folders/77")

    def test_only_the_requester_sees_a_request(self):
        p, _ = make()
        run_id = p.request_schema("fin", ANA)
        self.assertIsNotNone(p.run("fin", run_id, ANA))
        self.assertIsNone(p.run("fin", run_id, BO), "another user cannot read the request by its run ID")
        self.assertEqual(p.runs([f"fin/{run_id}"], BO), {})

    def test_polling_shares_calls_and_a_finished_run_is_read_once(self):
        p, fake = make()
        run_id = p.request_schema("fin", ANA)
        for _ in range(5):
            p.run("fin", run_id, ANA)
        self.assertEqual(fake.get_runs, 1, "polls within a few seconds share one Jobs API call")
        p.run_cache_seconds = 0
        fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        p.run("fin", run_id, ANA)
        calls = fake.get_runs
        for _ in range(5):
            p.run("fin", run_id, ANA)
        self.assertEqual(fake.get_runs, calls, "a finished run never changes, so it is not read again")


class Schemas(unittest.TestCase):
    def test_a_project_schema_runs_the_same_job_with_its_name(self):
        p, fake = make()
        run_id = p.request_schema("fin", ANA, schema="sales_bookings", reason=WHY)
        self.assertEqual((fake.started[0][1]["schema"], fake.started[0][1]["owner_group"]), ("sales_bookings", ""))
        self.assertEqual(p.run("fin", run_id, ANA).task, "Request a project schema")
        self.assertEqual(p.run("fin", run_id, ANA).resource, "fin_citizen_dev.sales_bookings")

    def test_a_team_schema_is_also_its_groups(self):
        # Any Entra group the requester names: the hub cannot see their groups, so membership is not checked.
        p, fake = make()
        run_id = p.request_schema("fin", ANA, schema="fin_reporting", owner_group="fin-finance", reason=WHY)
        self.assertEqual(fake.started[0][1]["owner_group"], "fin-finance", "a group they may not be in")
        self.assertEqual(p.run("fin", run_id, ANA).task, "Request a team schema")
        with self.assertRaisesRegex(portal.RequestError, "must be an Entra ID group's name"):
            p.request_schema("fin", ANA, schema="fin_other", owner_group="fin`; DROP", reason=WHY)
        with self.assertRaisesRegex(portal.RequestError, "needs a name"):
            p.request_schema("fin", ANA, owner_group="fin-data-eng")
        self.assertEqual(len(fake.started), 1)

    def test_named_schemas_and_folders_say_why_personal_schemas_need_not(self):
        p, fake = make()
        for call in (lambda r: p.request_schema("fin", ANA, schema="sales_forecast", reason=r),
                     lambda r: p.request_folder("fin", ANA, "fin-docs", reason=r)):
            for r in ("", "because", "x" * 1001):
                with self.subTest(reason=r[:20]), self.assertRaises(portal.RequestError):
                    call(r)
        self.assertEqual(fake.started, [])
        p.request_schema("fin", ANA)   # a personal schema: no reason needed
        run_id = p.request_schema("fin", ANA, schema="sales_forecast", reason=WHY)
        self.assertEqual(fake.started[-1][1]["reason"], WHY)
        self.assertEqual(p.run("fin", run_id, ANA).params["reason"], WHY, "kept with the request")

    def test_bad_custom_names_are_refused(self):
        p, fake = make()
        for name in ("Sales Bookings", "sales-bookings", "cd_bo", "_x", "x" * 101):
            with self.subTest(name=name), self.assertRaises(portal.RequestError):
                p.request_schema("fin", ANA, schema=name, reason=WHY)
        self.assertEqual(fake.started, [])

    def test_one_personal_schema_per_person(self):
        p, fake = make()
        self.assertEqual(p.personal_schema("fin", ANA)["exists"], False)
        fake.schemas_.add("fin_citizen_dev.cd_ana")
        p._personal.clear()
        found = p.personal_schema("fin", ANA)
        self.assertEqual((found["exists"], found["name"]), (True, "fin_citizen_dev.cd_ana"))

    def test_without_browse_it_is_unknown(self):
        p, fake = make()
        fake.schemas_ = None
        listed = []
        fake.jobs.list_runs = lambda **kw: listed.append(kw.get("active_only")) or []
        self.assertIsNone(p.personal_schema("fin", ANA)["exists"], "unknown, not 0/1")
        self.assertEqual(listed, [True], "only the running requests: no reading the history to guess")


class AICheck(unittest.TestCase):
    """Validate: rules first, then one call to the AI model; advice for the requester, it decides nothing."""

    def check(self, **kw):
        p, fake = make()
        args = {"ws_name": "fin", "kind": "project_schema", "name": "sales_pipeline_forecast", "reason": WHY, **kw}
        return p, fake, p.ai_check(**args)

    def test_a_clear_request_passes_every_check_in_one_call(self):
        p, fake, result = self.check()
        self.assertEqual(result["rows"], [(True, "The schema name is available"), (True, "The name matches the reason"),
                                          (True, "The reason says what it's for and who will use it")])
        self.assertEqual(len(fake.decided), 1, "one call, two questions")
        body = fake.decided[0]
        self.assertEqual(body["model"], "system.ai.claude-sonnet-5-5", "the AI model (Settings > AI)")
        system, asked = body["messages"]
        self.assertEqual(system["content"], portal.checks.PROMPT.replace("{noun}", "schema"), "the instructions never contain what the person typed")
        self.assertNotIn(WHY, system["content"])
        self.assertEqual(json.loads(asked["content"])["why_needed"], WHY, "the request, as data")
        p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual(len(fake.decided), 1, "asking again is answered from the cache")

    def test_it_shows_how_to_write_a_good_name_and_reason(self):
        p, fake = make()
        fake.decide.update(name="unclear", reason="unclear")
        rows = p.ai_check("fin", "project_schema", "sales_data", WHY)["rows"]
        self.assertIn((False, "Use a name that says what it holds, for example: sales_forecast_weekly"), rows)
        self.assertIn((False, "Say what it's for and who will use it, for example: weekly sales forecast tables for the sales operations team"), rows)
        p, fake = make()
        fake.decide.update(reason="unclear")
        rows = p.ai_check("fin", "folder", "fin-docs", WHY)["rows"]
        self.assertIn((False, "Say what it's for and who will use it, for example: notebooks and dashboards for the weekly sales forecast, used by the sales operations team"), rows)
        self.assertIn("Databricks folder", fake.decided[0]["messages"][0]["content"], "a folder is asked about as a folder")

    def test_an_answer_that_is_not_one_of_the_choices_is_not_a_pass(self):
        p, fake = make()
        fake.decide = {"name": "great", "reason": "clear"}
        rows = p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)["rows"]
        self.assertIn((False, "The name could not be checked"), rows)
        self.assertIn((True, "The reason says what it's for and who will use it"), rows)

    def test_without_an_ai_model_validate_checks_the_rules_only(self):
        p, fake = make()
        p.config = {**p.config, "ai": {"model": ""}}
        result = p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual((result["rows"], result["error"], fake.decided), ([(True, "The schema name is available")], "", []))

    def test_the_ai_check_runs_in_the_hub_not_the_requests_workspace(self):
        p, spoke = make()
        hub = FakeClient()
        p.client = lambda host: hub if host is None else spoke
        p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual((len(hub.decided), len(spoke.decided)), (1, 0), "through the hub's AI gateway")

    def test_rules_come_first_and_cost_no_call(self):
        p, fake = make()
        result = p.ai_check("fin", "project_schema", "cd_bo", WHY)
        self.assertEqual(fake.decided, [])
        self.assertIn("can't start with cd_", result["rows"][0][1])
        result = p.ai_check("fin", "folder", "fin-docs", "short")
        self.assertEqual(result["rows"], [(False, "Describe what it will be used for in a sentence or two.")])
        fake.schemas_.add("fin_citizen_dev.sales_pipeline_forecast")
        result = p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual(result["rows"][0], (False, "The schema name is already taken (fine only if it is yours)"))

    def test_a_folder_someone_else_owns_is_taken(self):
        p, fake = make()
        self.assertEqual(p.ai_check("fin", "folder", "fin-docs", WHY)["rows"][0], (True, "The folder name is available"))
        fake.folders_["/Workspace/fin-ops"] = "theirs"
        self.assertEqual(p.ai_check("fin", "folder", "fin-ops", WHY)["rows"][0], (False, "The folder name is already taken (fine only if it is yours)"))

    def test_a_lookup_that_cannot_answer_never_says_the_name_is_free(self):
        p, fake = make()
        fake.schemas_ = None   # the app cannot see the catalog
        result = p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual(result["rows"][0], (False, "Could not confirm the schema name is available"))

    def test_when_the_model_cannot_answer_it_says_so_and_decides_nothing(self):
        p, fake = make()
        fake.decide = None
        result = p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)
        self.assertEqual(result["error"], "The AI check is unavailable (ConnectionError)")
        fake.decide = dict(portal.checks.SAFE)
        self.assertEqual(p.ai_check("fin", "project_schema", "sales_pipeline_forecast", WHY)["error"], "", "a failure is not cached")


class RequestsInTheDatabase(unittest.TestCase):
    """With a database: every request is recorded before its job runs, and My requests reads it."""

    def test_a_request_is_recorded_then_run_then_linked_to_its_run(self):
        db = FakeStore()
        p, fake = make(db)
        run_id = p.request_schema("fin", ANA, schema="sales_forecast", reason=WHY)
        (rid, r), = db.requests.items()
        self.assertEqual((r["kind"], r["name"], r["bu"], r["reason"]), ("project_schema", "sales_forecast", "FIN", WHY))
        self.assertEqual(fake.started[0][1]["request_id"], rid, "the job gets the request's ID")
        self.assertEqual([e[1] for e in db.events], ["submitted", "run_started"], "no AI review is kept: approvers read the AI summary")
        self.assertEqual(db.events[-1][2], {"workspace": "fin", "run_id": run_id})

    def test_nothing_runs_when_the_request_cannot_be_recorded(self):
        db = FakeStore()
        db.fail = "write"
        p, fake = make(db)
        with self.assertRaisesRegex(portal.RequestError, "could not be recorded"):
            p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        self.assertEqual(fake.started, [])

    def test_the_approvals_app_reads_a_run_once_and_a_finished_one_never_again(self):
        p, fake = make()
        run_id = p.request_schema("fin", ANA)
        fake.get_runs = 0
        self.assertEqual(p.run_status("fin", run_id), "In progress")
        self.assertEqual(fake.get_runs, 1, "one call for the status (no output, no second read)")
        p.run_cache_seconds = 0
        fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        self.assertEqual(p.run_status("fin", run_id), "Completed", "in progress: read again")
        calls = fake.get_runs
        self.assertEqual(p.run_status("fin", run_id), "Completed")
        self.assertEqual(fake.get_runs, calls, "finished: never read again")
        self.assertEqual(p.run_status("fin", 999999), "Finished", "the Jobs API no longer has it")

    def test_a_run_that_does_not_exist_is_not_found(self):
        p, _ = make()
        self.assertIsNone(p.run("fin", 999999, ANA), "a page saying not found, not an error page")

    def test_an_approved_request_whose_workspace_is_gone_is_recorded_as_failed(self):
        db = FakeStore()
        p, _ = make(db)
        row = {"id": "ss-1", "kind": "folder", "workspace": "retired", "bu": "FIN", "requested_by": ANA, "name": "fin-docs",
               "owner_group": None, "reason": WHY}
        with self.assertRaises(portal.RequestError):
            p.run_recorded(row)
        self.assertEqual(db.events[-1][1:], ("start_failed", {"body": "The job could not be started."}))

    def test_an_ai_summary_that_fails_never_blocks_a_request(self):
        db = FakeStore()
        p, fake = make(db)
        p.config = {**p.config, "human_approval": ["project_schema"], "ai": {"model": "system.ai.some-model"}}
        with mock.patch.object(portal.summary_module, "summarize", side_effect=ConnectionError("model down")):
            request_id = p.request_schema("fin", ANA, schema="fin_forecast", reason=WHY)
            self.assertRegex(request_id, r"^ss-", "recorded and waiting for an approver")
            row = {"id": request_id, "kind": "project_schema", "workspace": "fin", "requested_by": ANA, "name": "fin_forecast"}
            self.assertIsNone(p.summarize(row), "the approvals app opens it with no summary, not an error")
        self.assertEqual(fake.started, [], "nothing ran: it waits for the approver")

    def test_a_job_that_cannot_start_is_recorded_as_failed(self):
        db = FakeStore()
        p, fake = make(db)
        fake.jobs.run_now = lambda job_id, job_parameters: (_ for _ in ()).throw(ConnectionError("down"))
        with self.assertRaisesRegex(portal.RequestError, "its job could not be started"):   # a message, not an error page
            p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        self.assertEqual(db.events[-1][1:], ("start_failed", {"body": "The job could not be started."}))
        self.assertEqual([(r.status, r.message) for r in p.requests(ANA)], [("Failed", "The job could not be started.")])

    def test_the_schema_job_is_told_the_comment_model_as_the_settings_are_when_it_runs(self):
        db = FakeStore()
        p, fake = make(db)
        shown = {"ai": {"model": "system.ai.claude-sonnet-5-5"}}
        p.shown = lambda: shown
        p.request_schema("fin", ANA, schema="sales_forecast", reason=WHY)
        self.assertEqual(fake.started[-1][1]["comment_model"], "system.ai.claude-sonnet-5-5")
        shown["ai"]["model"] = ""   # an admin turned AI off in Settings
        p.run_recorded({"id": "ss-p1", "kind": "project_schema", "workspace": "fin", "requested_by": ANA, "name": "sales_more", "reason": WHY})
        self.assertEqual(fake.started[-1][1]["comment_model"], "")
        self.assertEqual(p.settings_for("team_folder"), {}, "only the schema job")

    def test_an_approved_request_runs_as_it_was_recorded(self):
        """Portal.run_recorded: the approvals app runs the request's job with the request's own ID."""
        db = FakeStore()
        p, fake = make(db)
        row = {"id": "ss-team1", "kind": "team_schema", "workspace": "fin", "requested_by": ANA, "name": "fin_reporting",
               "owner_group": "fin-data-eng", "reason": WHY}
        run_id = p.run_recorded(row)
        job_id, params = fake.started[-1]
        self.assertEqual(params, {"user": ANA, "catalog": "fin_citizen_dev", "schema": "fin_reporting",
                                  "owner_group": "fin-data-eng", "reason": WHY, "request_id": "ss-team1", "temporary": "",
                                  "comment_model": "system.ai.claude-sonnet-5-5"})
        self.assertEqual(db.events[-1], ("ss-team1", "run_started", {"workspace": "fin", "run_id": run_id}))
        p.run_recorded({**row, "id": "ss-f1", "kind": "folder", "name": "fin-docs"})
        self.assertEqual(fake.started[-1][1], {"folder": "fin-docs", "requested_by": ANA, "owner_group": "fin-data-eng",
                                               "reason": WHY, "request_id": "ss-f1"})

    def test_a_runs_outcome_is_never_copied_into_the_database(self):
        db = FakeStore()
        p, fake = make(db)
        p.run_cache_seconds = 0
        run_id = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        self.assertEqual(p.run("fin", run_id, ANA).status, "Completed")
        self.assertEqual([e[1] for e in db.events], ["submitted", "run_started"], "the Jobs API is the source of truth")

    def test_an_expired_run_says_so_rather_than_guessing(self):
        db = FakeStore()
        p, fake = make(db)
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        fake.jobs.get_run = lambda run_id: (_ for _ in ()).throw(ValueError(f"Run {run_id} does not exist."))
        p._runs.clear()
        (r,) = p.requests(ANA)
        self.assertEqual((r.status, r.message), ("Finished", "Run details have expired (the Jobs API keeps 60 days)"))
        fake.jobs.get_run = lambda run_id: (_ for _ in ()).throw(ConnectionError("timed out"))
        p._runs.clear()
        (r,) = p.requests(ANA)
        self.assertEqual(r.status, "Unknown", "a network error is not an answer")

    def test_my_requests_come_from_the_database_however_old(self):
        db = FakeStore()
        p, fake = make(db)
        p.run_cache_seconds = 0
        first = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        p.request_schema("fin", ANA, schema="sales_forecast", reason=WHY)
        fake.runs_[first].state = state("TERMINATED", "SUCCESS")
        for i in range(300):                        # far more runs by others than any one listing of a job's runs
            fake.runs_[1000 + i] = run_of(1000 + i, 2, {"folder": f"x{i}", "requested_by": BO})
        p._runs.clear()
        calls = fake.get_runs
        items = p.requests(ANA)
        self.assertEqual([r.task for r in items], ["Request a project schema", "Request a workspace folder"])
        self.assertEqual(items[1].status, "Completed")
        self.assertEqual(fake.get_runs - calls, 2, "each request's status comes from its run")
        self.assertEqual(p.requests(BO), [], "only the person's own")

    def test_the_database_is_the_only_list_of_requests(self):
        db = FakeStore()
        p, fake = make(db)
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        db.fail = "read"
        with self.assertRaisesRegex(portal.RequestError, "cannot be read just now"):
            p.requests(ANA)   # no second path: the job runs are not read instead
        p.store = None
        with self.assertRaisesRegex(portal.RequestError, "not set up"):
            p.request_folder("fin", ANA, "fin-docs2", reason=WHY)
        self.assertEqual(len(fake.started), 1, "nothing runs without a record")


class ChosenBusinessUnit(unittest.TestCase):
    """Without a lookup function, people choose their business unit once, and may change it."""

    def test_they_are_asked_until_they_choose_then_requests_go_there(self):
        p, _ = make()
        self.assertEqual(p.business_units(), ["FIN", "OPS"])
        self.assertTrue(p.needs_bu_choice(ANA))
        self.assertIsNone(p.bu_of(ANA))
        p.choose_bu(ANA, "fin")
        self.assertFalse(p.needs_bu_choice(ANA))
        self.assertEqual(p.bu_of(ANA), "FIN")
        self.assertEqual([w.name for w in p.workspaces_for(ANA, "team_folder")], ["fin"])
        self.assertTrue(p.genie_one(ANA).startswith(HOST), "Genie One opens in their business unit's workspace")

    def test_they_can_change_it(self):
        p, _ = make()
        p.choose_bu(ANA, "FIN")
        p.choose_bu(ANA, "OPS")
        self.assertEqual(p.bu_of(ANA), "OPS")
        with self.assertRaises(portal.RequestError):
            p.workspaces_for(ANA, "team_folder")   # OPS's workspace is unreachable here: no workspace for it

    def test_only_a_business_unit_the_app_serves(self):
        p, _ = make()
        with self.assertRaises(portal.RequestError):
            p.choose_bu(ANA, "HR")

    def test_the_lookup_function_decides_when_there_is_one(self):
        p, _ = make()
        p.config = {**p.config, "bu_lookup": {"function": "dir.people.business_unit_of", "warehouse_id": "wh1", "host": HOST}}
        self.assertFalse(p.needs_bu_choice(ANA))
        with self.assertRaises(portal.RequestError):
            p.choose_bu(ANA, "FIN")


class BusinessUnitRouting(unittest.TestCase):
    """app.yaml bu_lookup: requests go to the person's own business unit's workspace."""

    def make(self, store=None):
        p, fake = make(store)
        p.config = {**p.config, "bu_lookup": {"function": "dir.people.business_unit_of", "warehouse_id": "wh1", "host": HOST}}
        return p, fake

    def test_opening_the_workspace_gives_the_guided_tour_the_first_time(self):
        p, _ = self.make()
        tour = "https://adb-1.azuredatabricks.net/one/chat?o=1&q=Onboard%20me%20%26%20show%20my%20data%3F"
        self.assertEqual(p.open_workspace(ANA, "Onboard me & show my data?"), tour, "the first time: the tour")
        self.assertEqual(p.store.tours, [ANA])
        self.assertEqual(p.open_workspace(ANA, "Onboard me & show my data?"), "https://adb-1.azuredatabricks.net/one/chat?o=1", "then plain Genie One")
        self.assertEqual(p.open_workspace(ANA, "Onboard me & show my data?", tour=True), tour, "the tour again, when asked")
        self.assertEqual(p.store.tours, [ANA, ANA], "each tour is a row")
        self.assertIsNone(p.open_workspace(BO, "Onboard me"), "the lookup does not know them: no workspace")

    def test_without_a_prompt_genie_one_opens_plain_and_no_tour_is_recorded(self):
        p, _ = make()
        self.assertEqual(p.open_workspace(ANA, ""), "https://adb-1.azuredatabricks.net/one/chat?o=1")
        self.assertFalse(p.toured(ANA))

    def test_a_tour_had_before_a_restart_is_remembered_from_the_database(self):
        p, _ = make()
        p.store.tours = [ANA]                                   # recorded by the app before it restarted
        self.assertEqual(p.open_workspace(ANA, "Onboard me"), "https://adb-1.azuredatabricks.net/one/chat?o=1", "plain Genie One")
        with mock.patch.object(p.store, "toured", side_effect=AssertionError("read again")):
            self.assertTrue(p.toured(ANA), "kept once read")

    def test_the_approvers_summary_uses_the_ai_model_from_settings(self):
        p, _ = make()
        row = {"id": "ss-1", "kind": "project_schema", "workspace": "fin", "requested_by": ANA, "name": "fin_forecast", "reason": WHY}
        p.shown = lambda: {"ai": {"model": ""}}
        self.assertIsNone(p.summarize(row), "no AI model: no summary")
        p.shown = lambda: {"ai": {"model": "system.ai.from-settings"}}
        with mock.patch.object(portal.summary_module, "summarize", return_value={"headline": "h", "model": "system.ai.from-settings"}) as write:
            self.assertEqual(p.summarize(row)["headline"], "h")
        self.assertEqual(write.call_args.args[1], "system.ai.from-settings")
        self.assertEqual(p.store.events[-1][:2], ("ss-1", "reviewed"), "kept with the request")

    def test_the_tour_is_given_again_rather_than_never_when_the_database_fails(self):
        p, _ = make()
        with mock.patch.object(p.store, "toured", side_effect=ConnectionError("down")):
            self.assertIn("q=Onboard", p.open_workspace(ANA, "Onboard me"), "cannot read it: the tour")
        with mock.patch.object(p.store, "record_tour", side_effect=ConnectionError("down")):
            self.assertIn("q=Onboard", p.open_workspace(BO, "Onboard me"), "cannot record it: still the tour")
        self.assertIn("q=Onboard", p.open_workspace(BO, "Onboard me"), "and again next time")
        with mock.patch.object(p.store, "toured", side_effect=AssertionError("read again")):
            self.assertNotIn("q=", p.open_workspace(BO, "Onboard me"), "kept once recorded: not read again")
        p.store, p._toured = None, {}
        self.assertIn("q=Onboard", p.open_workspace(ANA, "Onboard me"), "no database: always the tour")
        self.assertIn("q=Onboard", p.open_workspace(ANA, "Onboard me"))

    def test_links_open_in_the_persons_own_workspace(self):
        p, _ = self.make()
        p.config = {**p.config, "workspaces": [{"name": "fin", "bu": "FIN", "host": "https://acme.azuredatabricks.net", "id": "42", "catalog": "fin_citizen_dev"}]}
        links = p.links_for(ANA, {"discover": "{host}/discover?o={workspace_id}", "wiki": "https://wiki", "sop": {"schema": None}})
        self.assertEqual(links, {"discover": "https://acme.azuredatabricks.net/discover?o=42", "wiki": "https://wiki", "sop": {"schema": None}},
                         "a custom URL: o= is Terraform's workspace ID")
        self.assertIsNone(p.links_for(BO, {"discover": "{host}/discover"})["discover"], "no workspace for them: no card")
        self.assertEqual(p.open_workspace(ANA, "Start with {catalog}"), "https://acme.azuredatabricks.net/one/chat?o=42&q=Start%20with%20fin_citizen_dev")
        self.assertEqual(portal.fill("I'm in {business_unit}; {catalog}", p.config["workspaces"][0]), "I'm in FIN; fin_citizen_dev",
                         "the guided tour names the person's business unit (its prefix)")

    def test_genie_one_needs_a_workspace_id_only_on_azure(self):
        self.assertEqual(portal.genie_one_link("https://dbc-123.cloud.databricks.com/", "Onboard me"),
                         "https://dbc-123.cloud.databricks.com/one/chat?q=Onboard%20me")

    def test_a_choice_that_cannot_be_read_is_never_none(self):
        p, _ = make()
        p.choose_bu(ANA, "FIN")
        p._chosen.clear()
        with mock.patch.object(p.store, "chosen_business_unit", side_effect=ConnectionError("down")):
            with self.assertRaises(portal.BusinessUnitUnavailable):
                p.chosen_bu(ANA)
            with self.assertRaises(portal.BusinessUnitUnavailable, msg="not cached: asked again"):
                p.needs_bu_choice(ANA)
        self.assertEqual(p.chosen_bu(ANA), "FIN", "read again once it answers")

    def test_without_the_lookup_every_workspace_is_offered(self):
        p, fake = make()
        self.assertEqual([w.name for w in p.workspaces_for(BO, "team_folder")], ["fin"])
        self.assertEqual(fake.statements, [])

    def test_a_person_is_offered_their_own_business_units_workspace(self):
        p, fake = self.make()
        self.assertEqual([w.name for w in p.workspaces_for(ANA, "team_folder")], ["fin"])
        (st,) = fake.statements
        self.assertEqual((st["warehouse_id"], st["statement"]), ("wh1", "SELECT `dir`.`people`.`business_unit_of`(:email)"))
        self.assertEqual(st["parameters"], [{"name": "email", "value": ANA, "type": "STRING"}], "the email is a parameter, never pasted into SQL")
        p.workspaces_for(ANA, "personal_schema")
        self.assertEqual(len(fake.statements), 1, "kept: asked once")

    def test_someone_the_lookup_does_not_know_is_sent_to_their_admin(self):
        p, fake = self.make()
        with self.assertRaisesRegex(portal.RequestError, "couldn't find your business unit.*platform admin"):
            p.workspaces_for(BO, "team_folder")
        with self.assertRaisesRegex(portal.RequestError, "couldn't find your business unit"):
            p.request_folder("fin", BO, "fin-docs", reason=WHY)
        self.assertEqual(fake.started, [])

    def test_a_request_for_another_business_units_workspace_is_refused(self):
        p, fake = self.make()
        fake.bus_[BO] = "OPS"   # OPS's workspace cannot be reached in the fake
        with self.assertRaisesRegex(portal.RequestError, "no workspace for this request|own business unit"):
            p.request_folder("fin", BO, "fin-docs", reason=WHY)
        self.assertEqual(fake.started, [])
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        self.assertEqual(len(fake.started), 1)

    def test_validate_never_looks_in_another_business_units_workspace(self):
        p, fake = self.make()
        fake.bus_[BO] = "OPS"
        with self.assertRaisesRegex(portal.RequestError, "no workspace for this request|own business unit"):
            p.ai_check("fin", "folder", "fin-docs", WHY, user=BO)
        self.assertEqual(fake.decided, [], "nothing looked up, nothing asked")
        self.assertTrue(p.ai_check("fin", "folder", "fin-docs", WHY, user=ANA)["rows"], "their own BU's: checked as before")

    def test_a_lookup_that_cannot_answer_says_so(self):
        p, fake = self.make()
        fake.bus_ = None
        with self.assertRaisesRegex(portal.RequestError, "can't be checked just now"):
            p.workspaces_for(ANA, "team_folder")


class RunLinks(unittest.TestCase):
    def test_an_admin_gets_the_runs_page_in_the_hub_where_the_job_runs(self):
        p, fake = make()
        job = p.workspaces()[0].jobs["team_folder"]["id"]
        self.assertEqual(p.run_link("fin", "folder", 42), f"{HUB}/jobs/{job}/runs/42", "the hub, not the request's workspace")
        self.assertIsNone(p.run_link("fin", "folder", None), "no run yet")
        self.assertIsNone(p.run_link("nowhere", "folder", 42))
        p.config = {k: v for k, v in p.config.items() if k != "hub_host"}
        self.assertIsNone(p.run_link("fin", "folder", 42), "a config.json without the hub: no link rather than a wrong one")


class JobTags(unittest.TestCase):
    """The jobs say where they put things (their tags); the app follows them."""

    def test_a_personal_prefix_other_than_cd(self):
        p, fake = make()
        fake.jobs_[0].settings.tags["cd_prefix"] = "sb_"
        first = p.request_schema("fin", ANA)
        self.assertEqual(p.run("fin", first, ANA).resource, "fin_citizen_dev.sb_ana")
        self.assertEqual(p.request_schema("fin", ANA), first, "still asked for: no second run")
        self.assertEqual(p.personal_schema("fin", ANA)["exists"], "pending")

    def test_a_folder_root_other_than_workspace(self):
        p, fake = make()
        fake.jobs_[1].settings.tags["cd_root"] = "/Workspace/Teams/"
        first = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        self.assertEqual(p.run("fin", first, ANA).resource, "/Workspace/Teams/fin-docs")
        self.assertEqual(p.request_folder("fin", ANA, "fin-docs", reason=WHY), first, "still asked for: no second run")
        with self.assertRaisesRegex(portal.RequestError, "Another request for this name is running"):
            p.request_folder("fin", BO, "fin-docs", reason=WHY)


class OneAtATime(unittest.TestCase):
    def test_asking_again_while_running_returns_the_same_request(self):
        p, fake = make()
        first = p.request_schema("fin", ANA)
        self.assertEqual(p.request_schema("fin", ANA), first, "no second run for the same schema")
        self.assertEqual(len(fake.started), 1)
        self.assertEqual(p.personal_schema("fin", ANA)["exists"], "pending")
        fake.runs_[first].state = state("TERMINATED", "SUCCESS")
        fake.schemas_.add("fin_citizen_dev.cd_ana")
        p.run_cache_seconds = 0
        p.run("fin", first, ANA)                                   # the status page sees it finish
        self.assertEqual(p.personal_schema("fin", ANA)["exists"], True, "1/1 straight away, not after a minute")
        self.assertNotEqual(p.request_schema("fin", ANA), first, "once done, asking again is a new (harmless) run")

    def test_other_schemas_and_folders_are_separate(self):
        p, fake = make()
        a = p.request_schema("fin", ANA)
        b = p.request_schema("fin", ANA, schema="sales_bookings", reason=WHY)
        self.assertNotEqual(a, b)
        self.assertEqual(p.request_schema("fin", ANA, schema="sales_bookings", reason=WHY), b)
        f1 = p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        self.assertEqual(p.request_folder("fin", ANA, "fin-docs", reason=WHY), f1)
        self.assertNotEqual(p.request_folder("fin", ANA, "fin-other", reason=WHY), f1)
        self.assertEqual(len(fake.started), 4)

    def test_requests_from_different_people_run_side_by_side(self):
        p, fake = make()
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        p.request_folder("fin", BO, "fin-reports", reason=WHY)
        p.request_schema("fin", ANA)
        p.request_schema("fin", BO)
        self.assertEqual(len(fake.started), 4, "nobody waits for anyone else's request")

    def test_a_name_someone_else_is_asking_for_is_refused_until_their_run_ends(self):
        p, fake = make()
        theirs = p.request_folder("fin", BO, "fin-docs", reason=WHY)
        p.request_schema("fin", BO, schema="sales_bookings", reason=WHY)
        with self.assertRaisesRegex(portal.RequestError, "Another request for this name is running"):
            p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        with self.assertRaisesRegex(portal.RequestError, "Another request for this name is running"):
            p.request_schema("fin", ANA, schema="sales_bookings", reason=WHY)
        self.assertEqual(len(fake.started), 2, "never two runs racing for one folder or schema")
        fake.runs_[theirs].state = state("TERMINATED", "SUCCESS")
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)   # then the job's own check decides (it is Bo's now)
        self.assertEqual(len(fake.started), 3)


class History(unittest.TestCase):
    def test_lists_only_the_users_requests_newest_first(self):
        p, fake = make()
        a = p.request_schema("fin", ANA)
        p.request_folder("fin", ANA, "fin-docs", reason=WHY)
        fake.runs_[999] = run_of(999, 1, {"user": BO, "catalog": "fin_citizen_dev"})
        items = p.requests(ANA)
        self.assertEqual([r.task for r in items], ["Request a workspace folder", "Create a personal schema"])
        self.assertTrue(all(r.run_id != 999 for r in items))
        self.assertEqual(items[1].run_id, a)


try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI is not installed")
class Cards(unittest.TestCase):
    """cards.py: the catalog's sections and cards."""

    def test_every_card_is_in_a_section_with_its_own_key_and_an_icon(self):
        import cards
        sections = {k for k, _ in cards.SECTIONS}
        keys = [c.key for c in cards.CARDS]
        self.assertEqual(len(keys), len(set(keys)), "keys are unique")
        icons = (APP / "templates/_icons.html").read_text()
        for c in cards.CARDS:
            with self.subTest(card=c.key):
                self.assertIn(c.section, sections)
                self.assertIn(f'name == "{c.icon or c.key}"', icons)
                self.assertFalse(c.href and c.link, "a task or a link, not both")

    def test_link_cards_wait_for_their_link_and_empty_sections_are_left_out(self):
        import cards
        shown = lambda groups: [c["card"].key for _, _, cs in groups for c in cs]
        bare = shown(cards.groups({}))
        self.assertNotIn("discover", bare)
        self.assertNotIn("open_workspace", bare)
        full = cards.groups({"discover": "https://d", "review_requests": "https://r", "workspace": "/open"})
        self.assertIn("discover", shown(full))
        opened = [c for _, _, cs in full for c in cs if c["card"].key == "open_workspace"]
        self.assertEqual([(c["href"], c["more"]) for c in opened], [("/open", None)], "no tour link without its link")
        toured = cards.groups({"workspace": "/open", "tour": "/open?tour=1"})
        self.assertEqual([c["more"] for _, _, cs in toured for c in cs if c["card"].key == "open_workspace"],
                         [("Restart guided tour", "/open?tour=1")])
        only_data = [(k, t, [c for c in cs if c["card"].section == "data"]) for k, t, cs in cards.groups({})]
        self.assertEqual([k for k, _, cs in cards.groups({}) if k == "data"], [], "Data has only link cards: hidden without links")

    def test_adding_a_group_is_a_link_coming_soon_until_it_is_set(self):
        import cards
        import settings
        card = lambda groups: next(c for _, _, cs in groups for c in cs if c["card"].key == "group_request")
        self.assertEqual((card(cards.groups({}))["ready"], card(cards.groups({}))["href"]), (False, ""), "no link yet: Coming soon")
        set_ = card(cards.groups({"group_request": "https://servicenow.example.com/add-group"}))
        self.assertEqual((set_["ready"], set_["external"], set_["href"]), (True, True, "https://servicenow.example.com/add-group"))
        self.assertEqual(set_["card"].opens, "Opens your organization's request form", "not Databricks")
        opens = {c.key: c.opens for c in cards.CARDS}
        self.assertEqual(opens["discover"], "Opens in Databricks · Workspace access required")
        self.assertEqual(opens["open_workspace"], "Opens in Databricks · Workspace access required")
        self.assertNotIn("group_request", settings.KINDS, "set in app.yaml (links.group_request), not in Settings, for now")

    def test_every_section_has_an_faq_setting(self):
        import cards
        import settings
        for key, title in cards.SECTIONS:
            self.assertEqual(settings.FAQS[key], title)


class Pages(unittest.TestCase):
    def setUp(self):
        import importlib
        import os
        import tempfile
        self.cfg = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(CONFIG, self.cfg)
        self.cfg.close()
        os.environ["PORTAL_CONFIG"] = self.cfg.name
        sys.modules.pop("main", None)
        self.main = importlib.import_module("main")
        self.main.PORTAL, self.fake = make()
        self.main.PORTAL.choose_bu(ANA, "FIN")   # the first step (test_the_business_unit_comes_first)
        self.http = TestClient(self.main.app)
        self.as_ana = {"X-Forwarded-Email": ANA}

    def test_every_page_renders(self):
        for path in ("/", "/schema", "/schema/project", "/schema/team", "/folder", "/persona", "/warehouses", "/requests"):
            with self.subTest(path=path):
                r = self.http.get(path, headers=self.as_ana)
                self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertNotIn('id="owner_group"', self.http.get("/folder", headers=self.as_ana).text, "no owner group: people share the folder themselves")

    def test_a_wrong_kind_is_not_found_or_refused(self):
        self.assertEqual(self.http.post("/schema/other", data={"workspace": "fin", "name": "x"}, headers=self.as_ana).status_code, 404)
        self.main.CONFIG["ai_check"] = "on"
        try:
            r = self.http.post("/api/check", data={"kind": "warehouse", "workspace": "fin", "reason": WHY}, headers=self.as_ana)
            self.assertEqual(r.status_code, 400, "only the kinds Validate knows")
        finally:
            self.main.CONFIG.pop("ai_check")

    def test_the_requests_page_polls_only_the_persons_own_runs(self):
        run_id = self.main.PORTAL.request_schema("fin", ANA)
        mine = self.http.get(f"/api/requests?ids=fin/{run_id},fin/424242,", headers=self.as_ana).json()
        self.assertEqual(set(mine), {f"fin/{run_id}"}, "unknown runs are left out; an empty id is ignored")
        self.assertEqual(mine[f"fin/{run_id}"]["status"], "In progress")
        self.assertEqual(self.http.get(f"/api/requests?ids=fin/{run_id}", headers={"X-Forwarded-Email": BO}).json(), {},
                         "someone else's run is not shown")
        self.assertEqual(self.http.get("/api/requests", headers=self.as_ana).json(), {})

    def test_folders_show_their_workspace_and_schemas_only_their_catalog(self):
        folder = self.http.get("/folder", headers=self.as_ana).text
        self.assertIn('value="FIN · fin" readonly', folder, "one workspace: shown, not hidden")
        for path in ("/schema", "/schema/project", "/schema/team"):
            with self.subTest(path=path):
                page = self.http.get(path, headers=self.as_ana).text
                self.assertNotIn(">Workspace<", page, "Unity Catalog requests are not tied to a workspace")
                self.assertIn('name="workspace" value="fin"', page, "still routed to the business unit's")

    def test_access_says_which_workspace_it_is_for(self):
        self.assertIn('<span class="strong">FIN · fin</span>', self.http.get("/persona", headers=self.as_ana).text)

    def test_a_choice_of_schemas_is_a_choice_of_catalog(self):
        two = [portal.Workspace("fin", "FIN", HOST), portal.Workspace("ops", "OPS", HOST)]
        for w, catalog in zip(two, ("fin_citizen_dev", "ops_citizen_dev")):
            w.jobs = {k: {"id": 1, "tags": {"cd_catalog": catalog}} for k in portal.TASKS}
        with mock.patch.object(self.main.PORTAL, "workspaces_for", return_value=two):
            page = self.http.get("/schema/project", headers=self.as_ana).text
            folder = self.http.get("/folder", headers=self.as_ana).text
        self.assertIn(">Catalog<", page)
        self.assertIn(">ops_citizen_dev</option>", page)
        self.assertIn(">OPS · ops</option>", folder)

    def test_tasks_say_how_they_are_approved(self):
        page = self.http.get("/", headers=self.as_ana).text
        self.assertIn("<h1>Citizen Development Tasks</h1>", page, "the catalog's heading: title case, the app's name")
        self.assertEqual(page.count("Auto-approved"), 5, "personal, project, team and temporary schemas, and folders (their job is in this hub)")
        self.assertEqual(page.count(">Approval required"), 1, "workspace access (approved in Entra)")
        self.assertIn("Approval required", self.http.get("/persona", headers=self.as_ana).text)
        self.assertIn("Auto-approved", self.http.get("/folder", headers=self.as_ana).text)

    def test_not_signed_in(self):
        self.assertEqual(self.http.get("/").status_code, 401)

    def test_submit_goes_to_the_status_page_which_polls(self):
        r = self.http.post("/schema", data={"workspace": "fin"}, headers=self.as_ana, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/requests/fin/100"))
        page = self.http.get("/requests/fin/100", headers=self.as_ana).text
        self.assertIn('data-poll="/api/requests/fin/100"', page)
        self.assertIn("under a minute", page)
        self.assertRegex(page, r'<h1 class="request-title">fin_citizen_dev\.cd_ana</h1>', "what was asked for leads the page")
        self.assertIn('<span class="k">Can manage</span> You', page)
        self.assertEqual(self.http.get("/api/requests/fin/100", headers=self.as_ana).json()["phase"], "Starting")
        self.assertEqual(self.http.get("/api/requests/fin/100", headers={"X-Forwarded-Email": BO}).status_code, 404)

    def test_the_catalog_shows_the_personal_schema_quota(self):
        self.assertIn(">0 of 1 used<", self.http.get("/", headers=self.as_ana).text)
        self.fake.schemas_.add("fin_citizen_dev.cd_ana")
        self.main.PORTAL._personal.clear()
        page = self.http.get("/", headers=self.as_ana).text
        self.assertIn(">1 of 1 used<", page)
        self.assertIn("Open schema", self.http.get("/schema", headers=self.as_ana).text, "the form, not the card, links to the schema")

    def test_a_running_request_shows_as_requested(self):
        self.http.post("/schema", data={"workspace": "fin"}, headers=self.as_ana)
        self.assertIn(">Requested<", self.http.get("/", headers=self.as_ana).text)
        form = self.http.get("/schema", headers=self.as_ana).text
        self.assertIn("Your request is in progress", form)
        self.assertIn('href="/requests/fin/100"', form)
        self.assertNotIn(">Request personal schema<", form)
        r = self.http.post("/schema", data={"workspace": "fin"}, headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/requests/fin/100", "a second submit goes to the running request")
        self.assertEqual(len(self.fake.started), 1)

    def test_project_schema_form(self):
        r = self.http.post("/schema/project", data={"reason": WHY, "workspace": "fin", "name": "cd_bo"}, headers=self.as_ana)
        self.assertIn("can&#39;t start with cd_", r.text)
        r = self.http.post("/schema/project", data={"reason": WHY, "workspace": "fin", "name": "sales_bookings", "owner_group": "fin-data-eng"},
                           headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual((self.fake.started[0][1]["schema"], self.fake.started[0][1]["owner_group"]), ("sales_bookings", ""),
                         "a project schema never takes a group, even if one is sent")

    def test_team_schema_form(self):
        page = self.http.get("/schema/team", headers=self.as_ana).text
        self.assertIn('<input id="owner_group" name="owner_group"', page, "typed: the hub cannot list a person's groups")
        r = self.http.post("/schema/team", data={"reason": WHY, "workspace": "fin", "name": "fin_reporting"}, headers=self.as_ana)
        self.assertIn("Give the Entra ID group", r.text)
        r = self.http.post("/schema/team", data={"reason": WHY, "workspace": "fin", "name": "fin_reporting", "owner_group": "users"}, headers=self.as_ana)
        self.assertIn("users is every user of a workspace", r.text, "not a workspace's own group: Unity Catalog cannot grant to it")
        r = self.http.post("/schema/team", data={"reason": WHY, "workspace": "fin", "name": "fin_reporting", "owner_group": "fin-finance"},
                           headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.status_code, 303, "any Entra group: membership is not checked")
        self.assertEqual(self.fake.started[0][1]["owner_group"], "fin-finance")
        status = self.http.get(r.headers["location"], headers=self.as_ana).text
        self.assertIn('<span class="k">Can manage</span> You and fin-finance', status)
        self.assertEqual(self.http.get("/schema/other", headers=self.as_ana).status_code, 404)

    def test_the_reason_is_asked_for_shown_and_kept_for_try_again(self):
        self.assertIn('name="reason"', self.http.get("/schema/project", headers=self.as_ana).text)
        self.assertIn('name="reason"', self.http.get("/folder", headers=self.as_ana).text)
        self.assertNotIn('name="reason"', self.http.get("/schema", headers=self.as_ana).text, "not for a personal schema")
        r = self.http.post("/folder", data={"workspace": "fin", "folder": "fin-docs", "reason": "short"}, headers=self.as_ana)
        self.assertIn("Describe what it will be used for in a sentence or two.", r.text)
        self.assertIn(">short</textarea>", r.text, "what they typed stays in the form")
        r = self.http.post("/folder", data={"workspace": "fin", "folder": "fin-docs", "reason": WHY}, headers=self.as_ana, follow_redirects=False)
        status = self.http.get(r.headers["location"], headers=self.as_ana).text
        self.assertIn(f'<dt>Why</dt><dd>{WHY}</dd>', status)
        req = self.main.PORTAL.run("fin", int(r.headers["location"].rsplit("/", 1)[1]), ANA)
        self.assertIn("reason=Monthly+reconciliation", self.main.retry_link(req))

    def test_validate_on_the_forms(self):
        self.main.CONFIG["ai_check"] = "on"
        try:
            self.assertIn('data-ai-check="team_schema"', self.http.get("/schema/team", headers=self.as_ana).text)
            self.assertIn('data-ai-check="folder"', self.http.get("/folder", headers=self.as_ana).text)
            r = self.http.post("/api/check", data={"kind": "project_schema", "workspace": "fin", "name": "sales_forecast", "reason": WHY}, headers=self.as_ana)
            self.assertNotIn("verdict", r.json(), "the checks only: no verdict")
            self.assertEqual(r.json()["rows"][0], {"ok": True, "text": "The schema name is available"})
            self.assertEqual(self.fake.started, [], "a check runs nothing")
            r = self.http.post("/schema/project", data={"workspace": "fin", "name": "sales_forecast", "reason": WHY}, headers=self.as_ana, follow_redirects=False)
            status = self.http.get(r.headers["location"], headers=self.as_ana).text
            self.assertIn('Not needed', status, "without human_approval a project schema runs when asked")
            self.assertNotIn('Name and reason: ', status, "the check is for the form, not the status page")
        finally:
            self.main.CONFIG.pop("ai_check")
        self.assertNotIn("data-ai-check", self.http.get("/folder", headers=self.as_ana).text, "off: no check")
        self.assertEqual(self.http.post("/api/check", data={"kind": "folder"}, headers=self.as_ana).status_code, 404)

    def test_the_check_advises_and_never_stops_a_request(self):
        for mode in ("on",):
            self.main.CONFIG["ai_check"] = mode
            try:
                page = self.http.get("/schema/project", headers=self.as_ana).text
                self.assertNotIn("data-required", page)
                self.assertIn(">Validate</button>", page)
                send = lambda name: self.http.post("/schema/project", data={"workspace": "fin", "name": name, "reason": WHY},
                                                   headers=self.as_ana, follow_redirects=False)
                self.fake.decide = {**portal.checks.SAFE, "reason": "unclear"}     # the check finds something
                self.assertEqual(send(f"sales_forecast_{mode}").status_code, 303, mode)
                self.fake.decide = None                                            # the model cannot answer
                self.assertEqual(send(f"sales_forecast_{mode}_two").status_code, 303, "sent anyway: the check is advice")
            finally:
                self.main.CONFIG.pop("ai_check")
                self.fake.decide = dict(portal.checks.SAFE)
        self.assertEqual(len(self.fake.started), 2)
        self.main.CONFIG["ai_check"] = "maybe"   # only on and off: anything else is off
        try:
            self.assertNotIn(">Validate</button>", self.http.get("/schema/project", headers=self.as_ana).text)
        finally:
            self.main.CONFIG.pop("ai_check")

    def test_the_persona_page_offers_every_persona_without_tracking_access(self):
        page = self.http.get("/persona", headers=self.as_ana).text
        self.assertNotIn("Current access", page, "what someone has is managed in ServiceNow, not shown here")
        self.assertNotIn("Ask a platform admin", page, "no link, no button: nothing to say")

    def test_persona_links_can_differ_per_business_unit(self):
        import settings
        self.assertIn("Persona request links · FIN", [t for t, _, _ in settings.SECTIONS], "a section per business unit")
        self.assertIn("persona_request.OPS.builder", settings.KINDS)
        overrides = {"persona_request.builder": {"value": "https://sn.example.com/builder"},
                     "persona_request.FIN.explorer": {"value": "https://sn.example.com/fin-explorer"}}
        with mock.patch.object(self.main, "SETTINGS", lambda: overrides):
            page = self.http.get("/persona", headers=self.as_ana).text   # Ana is in FIN
        self.assertIn('href="https://sn.example.com/fin-explorer"', page, "FIN's own link")
        self.assertIn('href="https://sn.example.com/builder"', page, "no FIN builder link: the general one")
        shown = settings.apply(self.main.CONFIG, overrides)["links"]["persona_request_by_bu"]
        self.assertEqual(shown["OPS"], {"explorer": None, "builder": None, "publisher": None}, "OPS has none of its own")

    def test_a_task_page_links_its_sop(self):
        self.main.CONFIG.setdefault("links", {})["sop"] = {"persona": "https://wiki.example.com/sop/access"}
        try:
            page = self.http.get("/persona", headers=self.as_ana).text
        finally:
            self.main.CONFIG["links"].pop("sop")
        self.assertIn('href="https://wiki.example.com/sop/access"', page.split('class="options"')[0], "in the page's heading, not only on the catalog card")
        self.assertIn("View the standard operating procedure", page)

    def test_forms_route_by_business_unit_and_healthz_checks_the_lookup(self):
        lookup = {"function": "dir.people.business_unit_of", "warehouse_id": "wh1", "host": HOST}
        self.main.PORTAL.config = {**self.main.PORTAL.config, "bu_lookup": lookup}
        self.main.CONFIG["bu_lookup"] = lookup
        try:
            self.assertNotIn("find your business unit", self.http.get("/folder", headers=self.as_ana).text)
            page = self.http.get("/folder", headers={"X-Forwarded-Email": BO}).text
            self.assertIn("find your business unit", page)
            self.assertNotIn("No workspace offers folders yet", page, "one reason, not two")
            self.assertEqual(self.http.get("/healthz").json()["bu_lookup"], "ok")
            self.fake.bus_ = None
            self.main.PORTAL._bus.clear()
            r = self.http.get("/healthz")
            self.assertEqual((r.status_code, r.json()["bu_lookup"]), (503, "warehouse unreachable"))
        finally:
            self.main.CONFIG.pop("bu_lookup")

    def test_healthz_says_whether_the_app_can_do_its_job(self):
        r = self.http.get("/healthz")
        self.assertEqual((r.status_code, r.json()["ok"]), (200, True))
        self.assertEqual(r.json()["workspaces"]["fin"], "2 self-service jobs")
        self.main.PORTAL.store = type("S", (), {"ping": lambda self: (_ for _ in ()).throw(AttributeError("no postgres"))})()
        try:
            r = self.http.get("/healthz")
        finally:
            self.main.PORTAL.store = FakeStore()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["database"], "AttributeError: no postgres", "the reason a deploy is broken, as the app sees it")

    def test_old_custom_schema_links_still_work(self):
        r = self.http.get("/schema/custom?name=sales_bookings", headers=self.as_ana, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (301, "/schema/project?name=sales_bookings"))

    def test_the_review_requests_tile_opens_catalog_explorer(self):
        self.assertNotIn("View data access requests", self.http.get("/", headers=self.as_ana).text)
        link = "https://adb-1.azuredatabricks.net/explore/data?o=1&requestsView=audit"
        self.main.CONFIG["links"]["review_requests"] = link
        try:
            page = self.http.get("/", headers=self.as_ana).text
        finally:
            self.main.CONFIG["links"].pop("review_requests")
        self.assertIn(f'href="{link.replace("&", "&amp;")}" target="_blank" rel="noopener">View data access requests</a>', page)

    def test_ask_a_question_opens_genie_one_in_the_persons_workspace(self):
        r = self.http.get("/ask", headers=self.as_ana, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "https://adb-1.azuredatabricks.net/one/chat?o=1"))
        with mock.patch.object(self.main.PORTAL, "genie_one", return_value=None):
            page = self.http.get("/ask", headers=self.as_ana)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Contact your platform admin", page.text, "no workspace for them: where to go instead")

    def test_the_catalog_has_a_quick_search_over_every_card(self):
        page = self.http.get("/", headers=self.as_ana).text
        self.assertIn('<input type="search" id="catalog-search"', page)
        self.assertIn('id="catalog-search-box" hidden', page, "shown by the script: without it, no search box that does nothing")
        self.assertEqual(page.count('class="card task'), page.count("data-search="), "every card can be found")
        self.assertIn('data-search="request a workspace folder create a shared workspace folder', page)
        self.assertIn('id="no-results" hidden', page)

    def test_the_business_unit_comes_first(self):
        as_bo = {"X-Forwarded-Email": BO}   # Bo has not chosen yet (Ana chose FIN in setUp)
        for path in ("/", "/folder", "/schema/project", "/persona"):
            with self.subTest(path=path):
                r = self.http.get(path, headers=as_bo, follow_redirects=False)
                self.assertEqual((r.status_code, r.headers["location"]), (303, f"/business-unit?next={path}"))
        form = self.http.get("/business-unit?next=/folder", headers=as_bo).text
        self.assertIn("Which business unit are you in?", form)
        self.assertIn(">Continue</button>", form)
        self.assertNotIn(">Cancel</a>", form, "nothing to go back to before choosing")
        self.assertIn('value="FIN"', form)
        self.assertIn('value="OPS"', form)
        r = self.http.post("/business-unit", data={"bu": "OPS", "next": "/folder"}, headers=as_bo, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/folder"), "back to where they were going")
        page = self.http.get("/", headers=as_bo).text
        self.assertIn('<span class="account-bu">OPS</span>', page, "shown in the account chip")
        self.assertIn('<a class="account" href="/business-unit"', page, "and changeable from there")
        change = self.http.get("/business-unit", headers=as_bo).text
        self.assertIn(">Save</button>", change)
        self.assertIn(">Cancel</a>", change)
        self.assertIn('value="OPS" checked', change)
        self.assertIn("Choose one of the business units", self.http.post("/business-unit", data={"bu": "HR"}, headers=as_bo).text)

    def test_a_form_posted_before_choosing_goes_to_the_choice(self):
        r = self.http.post("/folder", data={"workspace": "fin", "folder": "fin-docs", "reason": WHY},
                           headers={"X-Forwarded-Email": BO}, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/business-unit"))
        self.assertEqual(self.fake.started, [], "nothing runs")

    def test_no_business_unit_card_is_left_alone_on_a_row(self):
        for count, cols in ((2, 2), (3, 3), (4, 2), (5, 3), (6, 3)):
            workspaces = [{"name": f"ws{i}", "bu": f"B{i}", "host": HOST} for i in range(count)]
            with self.subTest(business_units=count), \
                    mock.patch.dict(self.main.CONFIG, {"workspaces": workspaces}), \
                    mock.patch.dict(self.main.PORTAL.config, {"workspaces": workspaces}):
                page = self.http.get("/business-unit", headers=self.as_ana).text
                self.assertIn(f'class="bu-options bu-cols-{cols}"', page)

    def test_a_database_that_does_not_answer_says_so_never_choose_again(self):
        as_bo = {"X-Forwarded-Email": BO}   # Bo has chosen: the database just cannot say so now
        self.main.PORTAL.choose_bu(BO, "OPS")
        self.main.PORTAL._chosen.clear()
        down = mock.patch.object(self.main.PORTAL.store, "chosen_business_unit", side_effect=ConnectionError("database unreachable"))
        with down:
            for path in ("/", "/folder", "/business-unit"):
                with self.subTest(path=path):
                    r = self.http.get(path, headers=as_bo, follow_redirects=False)
                    self.assertEqual(r.status_code, 503, "not a redirect to the choice: it could not be saved either")
                    self.assertIn("Your business unit can&#39;t be read just now", r.text)
            r = self.http.post("/folder", data={"workspace": "fin", "folder": "fin-docs", "reason": WHY}, headers=as_bo, follow_redirects=False)
            self.assertEqual(r.status_code, 503)
            self.assertEqual(self.fake.started, [], "nothing was sent")
        self.assertEqual(self.http.get("/", headers=as_bo, follow_redirects=False).status_code, 200, "back: the failure was not kept")

    def test_choosing_never_sends_someone_to_another_site(self):
        for nxt in ("https://evil.example.com", "//evil.example.com", "/\\evil.example.com", "/\tevil", "/business-unit"):
            with self.subTest(next=nxt):
                r = self.http.post("/business-unit", data={"bu": "FIN", "next": nxt}, headers=self.as_ana, follow_redirects=False)
                self.assertEqual(r.headers["location"], "/")

    def test_request_a_budget_policy_and_the_cost_dashboard_are_coming_soon(self):
        page = self.http.get("/", headers=self.as_ana).text
        compute = page[page.index("<h2>Compute &amp; cost"):]
        for name in ("Request a budget policy", "View compute costs", "Request classic compute access"):
            with self.subTest(card=name):
                card = compute[compute.rindex('<div class="card task', 0, compute.index(name)):][:1200]
                self.assertIn("is-soon", card)
                self.assertIn("Coming soon", card)
                self.assertNotIn('class="stretched"', card, "not a link yet")

    def test_the_discover_data_card_opens_the_discover_page(self):
        self.assertNotIn("Discover data", self.http.get("/", headers=self.as_ana).text, "no link: no card")
        self.main.CONFIG["links"]["discover"] = "https://adb-1.azuredatabricks.net/discover?o=1"
        try:
            page = self.http.get("/", headers=self.as_ana).text
        finally:
            self.main.CONFIG["links"].pop("discover")
        data = page[page.index("<h2>Data<"):]
        self.assertIn('href="https://adb-1.azuredatabricks.net/discover?o=1" target="_blank" rel="noopener">Discover data</a>', data, "in the Data section")

    def test_open_your_workspace_gives_the_tour_once_and_again_on_request(self):
        page = self.http.get("/", headers=self.as_ana).text
        self.assertIn('href="/open" target="_blank" rel="noopener">Open Databricks Genie One</a>', page)
        self.assertNotIn("Restart guided tour", page, "no prompt: no tour")
        r = self.http.get("/open", headers=self.as_ana, follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "https://adb-1.azuredatabricks.net/one/chat?o=1"))
        self.main.CONFIG["onboarding"] = {"prompt": "Onboard me"}
        try:
            page = self.http.get("/", headers=self.as_ana).text
            first = self.http.get("/open", headers=self.as_ana, follow_redirects=False).headers["location"]
            then = self.http.get("/open", headers=self.as_ana, follow_redirects=False).headers["location"]
            again = self.http.get("/open?tour=1", headers=self.as_ana, follow_redirects=False).headers["location"]
        finally:
            self.main.CONFIG.pop("onboarding")
        self.assertIn('href="/open?tour=1" target="_blank" rel="noopener">Restart guided tour', page)
        self.assertEqual((first, then, again), ("https://adb-1.azuredatabricks.net/one/chat?o=1&q=Onboard%20me",
                                                "https://adb-1.azuredatabricks.net/one/chat?o=1",
                                                "https://adb-1.azuredatabricks.net/one/chat?o=1&q=Onboard%20me"))
        with mock.patch.object(self.main.PORTAL, "my_workspace", return_value=None):
            self.assertNotIn("Open Databricks Genie One", self.http.get("/", headers=self.as_ana).text, "no workspace for them: no card")
            page = self.http.get("/open", headers=self.as_ana)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Contact your platform admin", page.text, "where to go instead")

    def test_each_section_links_its_faq_and_new_people_are_pointed_to_access(self):
        self.main.CONFIG["links"]["discover"] = "https://adb-1.azuredatabricks.net/discover?o=1"   # Data has only link cards
        try:
            page = self.http.get("/", headers=self.as_ana).text
        finally:
            self.main.CONFIG["links"].pop("discover")
        self.assertEqual([h for h in ("<h2>Get started<", "<h2>Data<", "<h2>Build<", "<h2>Compute &amp; cost<") if h in page],
                         ["<h2>Get started<", "<h2>Data<", "<h2>Build<", "<h2>Compute &amp; cost<"])
        self.assertNotIn('class="group-faq"', page, "no FAQ pages set, no FAQ links")
        self.assertIn('New here? Start with <a href="/persona">Request workspace access</a></p>', page, "no Ask a question: Open Databricks Genie One is the card")
        self.main.CONFIG["faq"] = {"getting_started": "https://wiki.contoso.com/start", "access": "https://wiki.contoso.com/access",
                                   "data": None, "workspace": "https://wiki.contoso.com/workspace"}
        try:
            page = self.http.get("/", headers=self.as_ana).text
        finally:
            self.main.CONFIG.pop("faq")
        self.assertEqual(page.count('class="group-faq"'), 2, "access and workspace have FAQ pages; data does not")
        self.assertIn('<a class="group-faq" href="https://wiki.contoso.com/access" target="_blank" rel="noopener">FAQ', page)
        self.assertIn('<a href="https://wiki.contoso.com/start" target="_blank" rel="noopener">How it works', page)

    def test_a_form_error_is_shown_on_the_form(self):
        r = self.http.post("/folder", data={"reason": WHY, "workspace": "fin", "folder": "Fin Docs"}, headers=self.as_ana)
        self.assertIn("The folder name must be lowercase letters, digits and dashes", r.text)
        self.assertEqual(self.fake.started, [])

    def test_in_databricks_apps_only_its_sign_in_counts(self):
        import importlib
        with mock.patch.dict("os.environ", {"PORTAL_USER": ANA}):
            sys.modules.pop("main", None)
            local = importlib.import_module("main")
            self.assertEqual(TestClient(local.app).get("/warehouses").status_code, 200, "locally, PORTAL_USER signs in")
            with mock.patch.dict("os.environ", {"DATABRICKS_APP_NAME": "cd-self-service"}):
                sys.modules.pop("main", None)
                deployed = importlib.import_module("main")
                self.assertEqual(TestClient(deployed.app).get("/warehouses").status_code, 401)
        sys.modules.pop("main", None)

    def test_the_favicon(self):
        self.assertIn('href="/static/favicon.svg"', self.http.get("/", headers=self.as_ana).text)
        self.assertEqual(self.http.get("/static/favicon.svg").headers["content-type"], "image/svg+xml")
        r = self.http.get("/favicon.ico", follow_redirects=False)   # browsers ask for it anyway
        self.assertEqual((r.status_code, r.headers["location"]), (301, "/static/favicon.svg"))



@unittest.skipIf(TestClient is None, "FastAPI is not installed")
class TemporarySchemas(unittest.TestCase):
    """A temporary schema: the requester's, <prefix>tmp_<name>, tagged to expire; one at a time (the job checks)."""

    def setUp(self):
        import importlib
        import os
        import tempfile
        cfg = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({**CONFIG, "temporary_days": 14, "ai_check": "on"}, cfg)
        cfg.close()
        os.environ["PORTAL_CONFIG"] = cfg.name
        sys.modules.pop("main", None)
        self.main = importlib.import_module("main")
        self.db = FakeStore()
        self.main.PORTAL, self.fake = make(self.db)
        self.main.PORTAL.config = self.main.CONFIG
        self.main.PORTAL.choose_bu(ANA, "FIN")
        self.http = TestClient(self.main.app)
        self.as_ana = {"X-Forwarded-Email": ANA}

    def test_the_card_and_the_form(self):
        page = self.http.get("/", headers=self.as_ana).text
        self.assertIn('href="/schema/temporary"', page)
        self.assertIn(">Create a temporary schema</a>", page)
        form = self.http.get("/schema/temporary", headers=self.as_ana).text
        self.assertIn("fin_citizen_dev.cd_tmp_</span>", form, "they type what follows cd_tmp_")
        self.assertIn('<span class="danger-text">Your temporary schema will be deleted after 14 days.</span>', form, "in red; app.yaml jobs.temporary_schema.days")
        self.assertIn("but you can't share it with others", form)
        self.assertIn("copy it to another schema before it expires. You can only have one temporary schema at a time.", form)
        self.assertIn('data-ai-check="temporary_schema"', form)

    def quota(self):
        self.main.PORTAL._personal.clear()
        page = self.http.get("/", headers=self.as_ana).text
        card = page[page.index("Create a temporary schema</a>") - 600:page.index("Create a temporary schema</a>") + 600]
        return next((q for q in ("0 of 1 used", "1 of 1 used", "Requested") if q in card), None)

    def test_one_temporary_schema_per_person_like_the_personal_one(self):
        import datetime as dt
        self.assertEqual(self.quota(), "0 of 1 used")
        self.http.post("/schema/temporary", data={"workspace": "fin", "name": "try_join", "reason": WHY}, headers=self.as_ana)
        (rid, row), = self.db.requests.items()
        row["created_at"] = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)   # asked just now
        run_id = max(self.fake.runs_)
        self.assertEqual(self.quota(), "Requested", "its run is still going")
        self.fake.runs_[run_id].state = state("TERMINATED", "SUCCESS")
        self.fake.schemas_.add("fin_citizen_dev.cd_tmp_try_join")
        self.assertEqual(self.quota(), "1 of 1 used")
        have = self.main.PORTAL.temporary_schema("fin", ANA)
        self.assertEqual((have["name"], have["expires"]), ("fin_citizen_dev.cd_tmp_try_join", (row["created_at"] + dt.timedelta(days=14)).date().isoformat()))
        r = self.http.post("/schema/temporary", data={"workspace": "fin", "name": "another", "reason": WHY}, headers=self.as_ana)
        self.assertIn("You already have a temporary schema, fin_citizen_dev.cd_tmp_try_join, until", r.text)
        self.assertEqual(len(self.fake.started), 1, "refused before any run")
        form = self.http.get("/schema/temporary", headers=self.as_ana).text
        self.assertIn("You already have a temporary schema", form)
        self.assertIn('<p class="mono">fin_citizen_dev.cd_tmp_try_join</p>', form)
        self.assertIn('href="https://adb-1.azuredatabricks.net/explore/data/fin_citizen_dev/cd_tmp_try_join" target="_blank" rel="noopener">Open schema',
                      form, "opens it in their own workspace, like the personal schema")
        self.assertNotIn('type="submit"', form, "nothing to send until it expires: Open schema instead")
        self.fake.schemas_.discard("fin_citizen_dev.cd_tmp_try_join")
        self.assertEqual(self.quota(), "0 of 1 used", "an admin dropped it: free again")
        self.fake.schemas_.add("fin_citizen_dev.cd_tmp_try_join")
        row["created_at"] -= dt.timedelta(days=15)
        self.assertEqual(self.quota(), "0 of 1 used", "expired: free again")

    def test_when_the_database_cannot_answer_the_quota_is_unknown_and_the_job_decides(self):
        self.db.fail = "read"
        self.main.PORTAL._personal.clear()
        self.assertEqual(self.main.PORTAL.temporary_schema("fin", ANA)["exists"], None)

    def test_a_temporary_schema_runs_the_schema_job_with_its_full_name(self):
        r = self.http.post("/schema/temporary", data={"workspace": "fin", "name": "try_join", "reason": WHY}, headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text[:300])
        job_id, params = self.fake.started[-1]
        self.assertEqual((job_id, params["schema"], params["temporary"], params["owner_group"]), (1, "cd_tmp_try_join", "true", ""))
        (rid, row), = self.db.requests.items()
        self.assertEqual((row["kind"], row["name"]), ("temporary_schema", "cd_tmp_try_join"))
        self.assertEqual(portal.record_params(row, self.main.PORTAL.workspaces()[0])["temporary"], "true", "run again as a temporary one")

    def test_the_name_and_reason_follow_the_rules(self):
        for data, message in (({"name": "cd_x", "reason": WHY}, "start with cd_"), ({"name": "x", "reason": "short"}, "Describe what it will be used for"),
                              ({"name": "", "reason": WHY}, "Give the schema a name")):
            with self.subTest(data=data):
                r = self.http.post("/schema/temporary", data={"workspace": "fin", **data}, headers=self.as_ana)
                self.assertIn(message, r.text)
        self.assertEqual(self.fake.started, [])

    def test_validate_looks_up_the_full_name(self):
        self.fake.schemas_.add("fin_citizen_dev.cd_tmp_taken")
        rows = self.main.PORTAL.ai_check("fin", "temporary_schema", "taken", WHY)["rows"]
        self.assertEqual(rows[0], (False, "The schema name is already taken (fine only if it is yours)"))
        asked = json.loads(self.fake.decided[-1]["messages"][1]["content"])
        self.assertEqual((asked["request_type"], asked["name"]), ("temporary schema", "cd_tmp_taken"), "the model reads it as a temporary schema")

    def test_a_temporary_schema_is_the_requesters_alone(self):
        with self.assertRaisesRegex(portal.RequestError, "yours alone"):
            self.main.PORTAL.request_schema("fin", ANA, schema="x", owner_group="fin-data-eng", reason=WHY, temporary=True)
        with self.assertRaisesRegex(portal.RequestError, "needs a name"):
            self.main.PORTAL.request_schema("fin", ANA, reason=WHY, temporary=True)

    def test_when_unity_catalog_cannot_answer_the_quota_is_unknown(self):
        import datetime as dt
        self.http.post("/schema/temporary", data={"workspace": "fin", "name": "try_join", "reason": WHY}, headers=self.as_ana)
        (rid, row), = self.db.requests.items()
        row["created_at"] = dt.datetime.now(dt.timezone.utc)
        self.fake.runs_[max(self.fake.runs_)].state = state("TERMINATED", "SUCCESS")
        self.fake.schemas_ = None   # the app cannot see the catalog
        self.main.PORTAL._personal.clear()
        self.assertIsNone(self.main.PORTAL.temporary_schema("fin", ANA)["exists"], "unknown: the job decides")

    def test_a_failed_one_is_asked_again_on_its_form(self):
        r = portal.Request("Create a temporary schema", "fin", "fin_citizen_dev.cd_tmp_try", "ss-1", "", "Failed", "", kind="personal_schema",
                           params={"schema": "cd_tmp_try", "temporary": "true", "reason": WHY})
        self.assertEqual(self.main.retry_link(r), "/schema/temporary?" + __import__("urllib.parse").parse.urlencode({"workspace": "fin", "name": "try", "reason": WHY}))
        self.assertEqual(self.main.check_kind(r), "temporary_schema")


class ManualFolders(unittest.TestCase):
    """With no folder job in the hub, a folder is made by hand: recorded, always for an approver,
    who creates it and approves it, which marks it done. Nothing runs."""

    def setUp(self):
        import importlib
        import os
        import tempfile
        cfg = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({**CONFIG, "human_approval": ["project_schema", "team_schema"], "folder_root": "/Workspace/Teams"}, cfg)
        cfg.close()
        os.environ["PORTAL_CONFIG"] = cfg.name
        sys.modules.pop("main", None)
        self.main = importlib.import_module("main")
        self.db = FakeStore()
        self.main.PORTAL, self.fake = make(self.db)
        self.fake.jobs_ = [j for j in self.fake.jobs_ if j.settings.tags.get("cd_self_service") != "team_folder"]   # not deployed
        self.main.PORTAL.config = self.main.CONFIG
        self.main.PORTAL.choose_bu(ANA, "FIN")
        self.http = TestClient(self.main.app)
        self.as_ana = {"X-Forwarded-Email": ANA}

    def send(self, folder="fin-close"):
        return self.http.post("/folder", data={"workspace": "fin", "folder": folder, "reason": WHY}, headers=self.as_ana, follow_redirects=False)

    def test_folders_are_made_by_hand_only_while_their_job_is_not_deployed(self):
        p = self.main.PORTAL
        self.assertEqual(p.manual(), {"folder"})
        self.assertEqual([w.name for w in p.available("team_folder")], ["fin"], "offered without its job")
        with_job, _ = make()
        self.assertEqual(with_job.manual(), set(), "the job is deployed again: folders run it")
        unread = [portal.Workspace("fin", "FIN", HOST), portal.Workspace("down", "OPS", "https://down")]
        for w in unread:
            w.error = "the hub's jobs cannot be read"
        with mock.patch.object(p, "workspaces", return_value=unread):
            self.assertEqual(p.manual(), set(), "the hub's jobs cannot be read: not a reason to make anything by hand")

    def test_the_card_and_the_form_say_an_approver_creates_it(self):
        page = self.http.get("/", headers=self.as_ana).text
        card = page[page.index("Request a workspace folder") - 300:page.index("Request a workspace folder") + 600]
        self.assertIn('href="/folder"', card)
        self.assertIn("Approval required", card)
        self.assertIn("An approver decides it in the approvals app", card)
        form = self.http.get("/folder", headers=self.as_ana).text
        self.assertIn("A platform admin creates this folder for you once they approve it", form)
        self.assertIn(">Submit request</button>", form)

    def test_a_folder_request_is_recorded_and_waits_nothing_runs(self):
        r = self.send()
        self.assertEqual(self.fake.started, [], "no job")
        self.assertRegex(r.headers["location"], r"^/request/ss-[0-9a-f]{8}$")
        (rid, row), = self.db.requests.items()
        self.assertEqual((row["kind"], row["name"]), ("folder", "fin-close"))
        page = self.http.get(r.headers["location"], headers=self.as_ana).text
        self.assertIn("Pending approval", page)
        self.assertIn("a platform admin creates it", page)
        self.assertNotIn(">Running<", page, "no run to wait for")
        self.assertEqual(self.send().headers["location"], r.headers["location"], "asked again: the one waiting")

    def test_approving_it_marks_it_done_and_runs_nothing(self):
        rid = self.send().headers["location"].rsplit("/", 1)[1]
        self.assertIsNone(self.main.PORTAL.run_recorded({**self.db.requests[rid], "id": rid}))
        self.assertEqual(self.fake.started, [])
        self.db.event(rid, "approved", actor="dana@contoso.com")
        page = self.http.get(f"/request/{rid}", headers=self.as_ana).text
        self.assertIn("Your folder is ready", page)
        self.assertIn("/Workspace/Teams/fin-close", page, "where the admin made it (app.yaml jobs.folder_root)")
        self.assertIn("Completed", page)
        mine = self.http.get("/requests", headers=self.as_ana).text
        self.assertIn("Completed", mine)

    def test_validate_never_looks_a_folder_up_in_the_hub(self):
        with mock.patch.object(self.fake.workspace, "get_status", side_effect=AssertionError("the hub has no folders of a spoke")):
            rows = self.main.PORTAL.ai_check("fin", "folder", "fin-close", WHY)["rows"]
        self.assertEqual(rows, [(True, "The name matches the reason"), (True, "The reason says what it's for and who will use it")])


class ApprovalRequests(unittest.TestCase):
    """human_approval: project and team schemas wait for an approver; the requester follows them
    on the request's page, answers questions there, and sees the decision."""

    def setUp(self):
        import importlib
        import os
        import tempfile
        cfg = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({**CONFIG, "human_approval": ["project_schema", "team_schema"]}, cfg)
        cfg.close()
        os.environ["PORTAL_CONFIG"] = cfg.name
        sys.modules.pop("main", None)
        self.main = importlib.import_module("main")
        self.db = FakeStore()
        self.main.PORTAL, self.fake = make(self.db)
        self.main.PORTAL.config = self.main.CONFIG
        self.main.PORTAL.choose_bu(ANA, "FIN")
        self.http = TestClient(self.main.app)
        self.as_ana = {"X-Forwarded-Email": ANA}

    def send(self, name="sales_forecast"):
        return self.http.post("/schema/project", data={"workspace": "fin", "name": name, "reason": WHY}, headers=self.as_ana, follow_redirects=False)

    def test_a_project_schema_is_recorded_and_waits_nothing_runs(self):
        r = self.send()
        self.assertEqual(self.fake.started, [], "no job until an approver approves")
        self.assertRegex(r.headers["location"], r"^/request/ss-[0-9a-f]{8}$")
        page = self.http.get(r.headers["location"], headers=self.as_ana).text
        self.assertIn("Waiting for an approver", page)
        self.assertIn("Pending approval", page)
        self.assertEqual(self.send().headers["location"], r.headers["location"], "asking again shows the one waiting")
        self.assertIn("Pending approval", self.http.get("/requests", headers=self.as_ana).text)
        self.assertIn(f'href="{r.headers["location"]}"', self.http.get("/requests", headers=self.as_ana).text)

    def test_the_catalog_and_the_form_say_an_approver_decides(self):
        self.assertEqual(self.http.get("/", headers=self.as_ana).text.count(">Approval required"), 3, "project and team schemas, and personas")
        form = self.http.get("/schema/project", headers=self.as_ana).text
        self.assertIn(">Submit request</button>", form)
        self.assertIn("Your schema will be created once approved.", form)

    def test_a_folder_that_needs_no_approver_says_create(self):
        form = self.http.get("/folder", headers=self.as_ana).text
        self.assertIn(">Create folder</button>", form)
        self.assertIn("Your folder will be ready in under a minute.", form)
        self.assertIn("Your workspace's platform admins can manage it too", form)

    def test_the_requester_answers_a_question_and_sees_the_decision(self):
        location = self.send().headers["location"]
        rid = location.rsplit("/", 1)[1]
        self.assertIn("Nobody is waiting for an answer", self.http.post(f"{location}/reply", data={"body": "Hi"}, headers=self.as_ana).text)
        self.db.event(rid, "needs_info", actor="dana@contoso.com", body="Which regions?")
        page = self.http.get(location, headers=self.as_ana).text
        self.assertIn("An approver asked you a question", page)
        self.assertIn("Which regions?", page)
        self.assertIn("Reply needed", self.http.get("/requests", headers=self.as_ana).text)
        r = self.http.post(f"{location}/reply", data={"body": "All of Canada."}, headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.db.events[-1][1:], ("replied", {"actor": ANA, "body": "All of Canada."}))
        self.assertIn("Waiting for an approver", self.http.get(location, headers=self.as_ana).text, "back with the approvers")
        self.db.event(rid, "rejected", actor="dana@contoso.com", body="Use the shared forecast schema.")
        page = self.http.get(location, headers=self.as_ana).text
        self.assertIn("Rejected by dana@contoso.com", page)
        self.assertIn("Use the shared forecast schema.", page)

    def test_the_status_page_keeps_the_conversation(self):
        rid = self.send().headers["location"].rsplit("/", 1)[1]
        self.db.event(rid, "needs_info", actor="dana@contoso.com", body="Which regions?")
        self.db.event(rid, "approved", actor="dana@contoso.com")
        run_id = self.main.PORTAL.run_recorded(dict(self.db.requests[rid]))
        page = self.http.get(f"/requests/fin/{run_id}", headers=self.as_ana).text
        self.assertIn(">Conversation<", page, "once it runs, the requester still sees what was asked and answered")
        self.assertIn("Which regions?", page)
        self.assertIn('<span class="event-pill approved">Approved</span>', page, "a decision is a pill")

    def test_my_requests_shows_how_many_need_a_reply(self):
        rid = self.send().headers["location"].rsplit("/", 1)[1]
        self.assertNotIn('class="nav-count"', self.http.get("/", headers=self.as_ana).text)
        self.db.event(rid, "needs_info", actor="dana@contoso.com", body="Which regions?")
        self.main.PORTAL._replies.clear()
        self.assertIn('class="nav-count" title="1 request needs your reply">1<', self.http.get("/", headers=self.as_ana).text)

    def test_the_summary_is_written_in_the_background_for_approvers(self):
        import threading
        self.main.CONFIG["ai"] = {"model": "system.ai.claude-sonnet-5-5"}   # Settings > AI, app.yaml's until changed
        self.fake.api_client = type("A", (), {"do": staticmethod(lambda method, path, body=None:
            {"choices": [{"message": {"content": '{"headline": "Project schema for forecasts", "summary": "s", "concerns": [], "questions": []}'}}]})})()
        rid = self.send().headers["location"].rsplit("/", 1)[1]
        for t in threading.enumerate():
            if t.daemon and t is not threading.current_thread():
                t.join(timeout=5)
        summaries = [d for r, t, d in self.db.events if r == rid and t == "reviewed" and "summary" in d]
        self.assertEqual(summaries[0]["summary"]["headline"], "Project schema for forecasts")

    def test_only_the_requester_sees_their_request(self):
        location = self.send().headers["location"]
        self.assertEqual(self.http.get(location, headers={"X-Forwarded-Email": "bo@contoso.com"}).status_code, 404)

    def test_the_run_page_names_who_approved_it(self):
        rid = self.send().headers["location"].rsplit("/", 1)[1]
        self.db.event(rid, "approved", actor="dana@contoso.com")
        run_id = self.main.PORTAL.run_recorded({**self.db.requests[rid], "id": rid})
        page = self.http.get(f"/requests/fin/{run_id}", headers=self.as_ana).text
        self.assertIn("Approved by dana@contoso.com", page)

    def test_once_its_job_runs_the_request_page_hands_over_to_the_run(self):
        location = self.send().headers["location"]
        rid = location.rsplit("/", 1)[1]
        self.db.event(rid, "approved", actor="dana@contoso.com")
        self.db.run_started(rid, "fin", 77)
        r = self.http.get(location, headers=self.as_ana, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/requests/fin/77")

    def test_folders_and_personal_schemas_still_run_when_asked(self):
        r = self.http.post("/folder", data={"workspace": "fin", "folder": "fin-docs", "reason": WHY}, headers=self.as_ana, follow_redirects=False)
        self.assertRegex(r.headers["location"], r"^/requests/fin/\d+$")
        self.assertEqual(len(self.fake.started), 1)


if __name__ == "__main__":
    unittest.main()
