"""The app's database (Lakebase Postgres): each request as asked, and what the app did with it.

Tables, view and grants come from db/ (applied by scripts/app_deploy.py); this module only reads and
appends: the app's role may SELECT and INSERT, never UPDATE or DELETE. It keeps only what the
app owns (the request, its AI summary, comments, decisions, the link to its job run, settings);
a run's outcome is read from the Jobs API, its source of truth, never copied here. Plain SQL, a
short connection per call, signed in with a Lakebase credential made for the app's own identity
(no password anywhere). Every install has its database; from_config is None only when
config.json has none (a misconfigured or local run), and the pages then say it is not set up.
"""
import json
import os
import threading
import time

# The kinds a request can be, as the database knows them (the portal's job kinds are coarser).
KINDS = ("personal_schema", "project_schema", "team_schema", "folder")


def db_kind(job_kind, params):
    """The request's kind, from the job it runs and its parameters."""
    if job_kind == "team_folder":
        return "folder"
    if params.get("schema"):
        return "team_schema" if params.get("owner_group") else "project_schema"
    return "personal_schema"


class Store:
    def __init__(self, database, credential=None, connect=None):
        """database: config.json's {"host", "name", "endpoint"}. credential() returns a fresh
        token and connect(**kwargs) a connection: the defaults use the Databricks SDK and
        psycopg; tests pass their own."""
        self.database = database
        self._credential = credential or self._lakebase_credential
        self._connect = connect
        self._token, self._token_at = None, 0
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config):
        db = config.get("database")
        return cls(db) if db and db.get("host") else None

    # ---- Connections ----

    def _lakebase_credential(self):
        from databricks.sdk import WorkspaceClient
        return WorkspaceClient().postgres.generate_database_credential(endpoint=self.database["endpoint"]).token

    def _conn(self):
        with self._lock:   # a credential lasts an hour; make a new one well before that
            if not self._token or time.time() - self._token_at > 45 * 60:
                self._token, self._token_at = self._credential(), time.time()
            token = self._token
        if self._connect:
            return self._connect(token=token)
        import psycopg
        user = os.environ.get("PGUSER") or os.environ.get("DATABRICKS_CLIENT_ID")
        return psycopg.connect(host=self.database["host"], dbname=self.database["name"], user=user,
                               password=token, sslmode="require", connect_timeout=30)

    def ping(self):
        """True if the app can sign in to its database and query it (for /healthz)."""
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM self_service.requests").fetchone() is not None

    # ---- Writing (append only) ----

    def record_request(self, r):
        """A new request and its first event (submitted), in one transaction: before its job
        runs, so every request that runs is recorded."""
        with self._conn() as c:
            c.execute("INSERT INTO self_service.requests (id, kind, workspace, bu, requested_by, name, owner_group, reason) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                      (r["id"], r["kind"], r["workspace"], r["bu"], r["requested_by"], r["name"], r.get("owner_group") or None, r.get("reason") or None))
            c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type, body) VALUES (%s, %s, 'requester', 'submitted', %s)",
                      (r["id"], r["requested_by"], r.get("reason") or None))

    def event(self, request_id, type_, actor="Citizen Development app", role="system", body=None, data=None):
        """Append an event. One that the database allows only once (a run starting or ending, a
        decision) is not an error the second time: it is already recorded."""
        with self._conn() as c:
            c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type, body, data) "
                      "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                      (request_id, actor, role, type_, body, json.dumps(data or {})))

    def summarized(self, request_id, summary, actor="AI summary"):
        """The model's summary of a request, for approvers (summary.py)."""
        self.event(request_id, "reviewed", actor=actor, data={"summary": summary})

    def decide(self, request_id, approver, outcome, body=None):
        """An approver's decision (approved, rejected) or question (needs_info). True if it was
        recorded; False if another approver decided first (the database keeps one decision)."""
        with self._conn() as c:
            row = c.execute("INSERT INTO self_service.request_events (request_id, actor, role, type, body) "
                            "VALUES (%s, %s, 'approver', %s, %s) ON CONFLICT DO NOTHING RETURNING id",
                            (request_id, approver, outcome, body or None)).fetchone()
        return row is not None

    def run_started(self, request_id, workspace, run_id):
        self.event(request_id, "run_started", data={"workspace": workspace, "run_id": int(run_id)})

    def start_failed(self, request_id, message):
        """The job could not be started: there is no run to read, so this is the app's to record.
        (A run's outcome is never kept here: the Jobs API is its source of truth.)"""
        self.event(request_id, "start_failed", body=message)

    # ---- Reading ----

    def requests_of(self, user, limit=200):
        """The person's requests, newest first, each with its latest state and its job run."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.id, s.kind, s.workspace, s.bu, s.name, s.owner_group, s.reason, s.created_at, "
                "       s.state, s.state_data, run.data, "
                "       (SELECT body FROM self_service.request_events b WHERE b.request_id = s.id AND b.type = s.state ORDER BY b.id DESC LIMIT 1) "
                "FROM self_service.request_status s "
                "LEFT JOIN self_service.request_events run ON run.request_id = s.id AND run.type = 'run_started' "
                "WHERE s.requested_by = %s ORDER BY s.created_at DESC LIMIT %s", (user, limit)).fetchall()
        out = []
        for rid, kind, ws, bu, name, group, reason, created, state, state_data, run, state_body in rows:
            run = run if isinstance(run, dict) else json.loads(run or "{}")
            state_data = state_data if isinstance(state_data, dict) else json.loads(state_data or "{}")
            out.append({"id": rid, "kind": kind, "workspace": ws, "bu": bu, "name": name, "owner_group": group,
                        "reason": reason, "created_at": created, "state": state, "state_data": state_data,
                        "state_body": state_body, "run_id": run.get("run_id"), "requested_by": user})
        return out

    # ---- Reading, for the approvals app (its role may read every request) ----

    def requests_in(self, bus, limit=300):
        """Requests in these business units, newest first, each with its latest state, its job
        run (if one started), its AI summary (if there is one), and its decision (if one was made)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.id, s.kind, s.workspace, s.bu, s.requested_by, s.name, s.owner_group, s.reason, s.created_at, "
                "       s.state, s.state_at, run.data, d.type, d.actor, d.at, d.body, summary.data "
                "FROM self_service.request_status s "
                "LEFT JOIN self_service.request_events run ON run.request_id = s.id AND run.type = 'run_started' "
                "LEFT JOIN LATERAL (SELECT data FROM self_service.request_events WHERE request_id = s.id AND type = 'reviewed' "
                "                   AND data ? 'summary' ORDER BY id DESC LIMIT 1) summary ON true "
                "LEFT JOIN self_service.request_events d ON d.request_id = s.id AND d.type IN ('approved', 'rejected') "
                "WHERE s.bu = ANY(%s) ORDER BY s.created_at DESC LIMIT %s", (list(bus), limit)).fetchall()
        load = lambda v: v if isinstance(v, dict) else json.loads(v or "{}")
        return [{"id": r[0], "kind": r[1], "workspace": r[2], "bu": r[3], "requested_by": r[4], "name": r[5],
                 "owner_group": r[6], "reason": r[7], "created_at": r[8], "state": r[9], "state_at": r[10],
                 "run": load(r[11]),
                 "decision": r[12] and {"outcome": r[12], "by": r[13], "at": r[14], "comment": r[15] or ""},
                 "summary": load(r[16]).get("summary")} for r in rows]

    def events_of(self, request_id):
        """Everything that happened to one request, in order."""
        with self._conn() as c:
            rows = c.execute("SELECT at, actor, role, type, body, data FROM self_service.request_events "
                             "WHERE request_id = %s ORDER BY at, id", (request_id,)).fetchall()
        return [{"at": r[0], "actor": r[1], "role": r[2], "type": r[3], "body": r[4],
                 "data": r[5] if isinstance(r[5], dict) else json.loads(r[5] or "{}")} for r in rows]

    # ---- The business unit people chose (without a lookup function) ----

    def chosen_business_unit(self, email):
        """The business unit this person last chose, or None."""
        with self._conn() as c:
            row = c.execute("SELECT bu FROM self_service.chosen_business_units WHERE email = %s", (email.lower(),)).fetchone()
        return row[0] if row else None

    def choose_business_unit(self, email, bu):
        with self._conn() as c:
            c.execute("INSERT INTO self_service.business_unit_choices (email, bu) VALUES (%s, %s)", (email.lower(), bu.upper()))

    # ---- The guided tour (the Open Databricks Genie One card) ----

    def toured(self, email):
        """Whether this person has had the guided tour."""
        with self._conn() as c:
            return c.execute("SELECT 1 FROM self_service.guided_tours WHERE email = %s LIMIT 1", (email.lower(),)).fetchone() is not None

    def record_tour(self, email):
        with self._conn() as c:
            c.execute("INSERT INTO self_service.guided_tours (email) VALUES (%s)", (email.lower(),))

    # ---- Settings (settings.py): app.yaml's values, overridden from the approvals app ----

    def settings(self):
        """Each setting someone changed: {key: {"value", "by", "at"}} (value None: back to app.yaml's)."""
        with self._conn() as c:
            rows = c.execute("SELECT key, value, actor, at FROM self_service.settings").fetchall()
        return {r[0]: {"value": r[1], "by": r[2], "at": r[3]} for r in rows}

    def set_settings(self, changes, actor):
        """Record changes [(key, value)] in one transaction (the approvals app only)."""
        with self._conn() as c:
            for key, value in changes:
                c.execute("INSERT INTO self_service.setting_events (key, value, actor) VALUES (%s, %s, %s)", (key, value, actor))

    def setting_history(self, limit=20, offset=0, keys=(), q="", q_keys=()):
        """Changes, newest first, each with the value before it ("first": the change before it
        was app.yaml's). keys: only these settings; q: words in a value or a person, or (q_keys)
        a setting whose name matches."""
        like = f"%{q.strip()}%"
        with self._conn() as c:
            rows = c.execute(
                "WITH h AS (SELECT id, key, value, actor, at, LAG(value) OVER (PARTITION BY key ORDER BY id) AS previous, "
                "                  ROW_NUMBER() OVER (PARTITION BY key ORDER BY id) AS n FROM self_service.setting_events) "
                "SELECT key, value, actor, at, previous, n FROM h "
                "WHERE (cardinality(%s::text[]) = 0 OR key = ANY(%s::text[])) "
                "  AND (%s = '' OR value ILIKE %s OR previous ILIKE %s OR actor ILIKE %s OR key = ANY(%s::text[])) "
                "ORDER BY id DESC LIMIT %s OFFSET %s",
                (list(keys), list(keys), q.strip(), like, like, like, list(q_keys), limit, offset)).fetchall()
        return [{"key": r[0], "value": r[1], "by": r[2], "at": r[3], "previous": r[4], "first": r[5] == 1} for r in rows]
