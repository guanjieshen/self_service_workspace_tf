"""The self-service portal's logic: find each workspace's self-service jobs, check a request,
run the job, and list a user's requests. main.py serves it over HTTP.

The app changes nothing itself: every request becomes a run of a job the bundle deployed
(bundle/jobs/notebooks/personal_schema.py and team_folder.py), run as the app's service
principal. The jobs check every request again. Every request is recorded in the app's
database first (store.py), and My requests reads it from there.
"""
import datetime
import json
import logging
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from databricks.sdk.errors import NotFound, PermissionDenied

import checks
import store as store_module
import summary as summary_module

# A failure the app works around (a fallback, an unknown answer) is still written to the app's
# log, so it is never silent: the database being unreachable once hid an outage for hours.
log = logging.getLogger("self-service")


def warn(what, e):
    log.warning("%s: %s: %s", what, type(e).__name__, str(e)[:300])

EMAIL = r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]+"
GROUP = r"[A-Za-z0-9 _.-]+"
APP_ID = r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"
FOLDER = r"[a-z0-9][a-z0-9-]*"
RESERVED_FOLDERS = ("users", "shared", "repos", "admin", "workspace")
# The workspace's own groups: a folder can be shared with them, but Unity Catalog grants only
# to account groups, so a team schema cannot go to these.
WORKSPACE_GROUPS = ("admins", "users")
TASKS = {"personal_schema": "Create a personal schema", "team_folder": "Request a workspace folder"}
# The personal schema job also makes named schemas: a project schema (the requester's) and a
# team schema (the requester's and one of their groups').
PROJECT_SCHEMA, TEAM_SCHEMA = "Request a project schema", "Request a team schema"
# How each task is approved, as the catalog and task pages label it. The app's own tasks run
# straight away (the jobs check every request); a persona is approved in Entra ID.
APPROVAL = {"schema": "auto", "project_schema": "auto", "team_schema": "auto", "folder": "auto", "persona": "required"}
APPROVAL_LABELS = {"auto": "Auto-approved", "required": "Approval required"}


def approval_of(config):
    """Each catalog task's approval, with the kinds an approver decides (app.yaml human_approval)."""
    people = set(config.get("human_approval", ()))
    task_kind = {"schema": "personal_schema", "project_schema": "project_schema", "team_schema": "team_schema", "folder": "folder"}
    return {**APPROVAL, **{task: "required" for task, kind in task_kind.items() if kind in people}}
SCHEMA = r"[a-z0-9][a-z0-9_]*"
# Where a run is, as the status page shows it: waiting for serverless compute, or running.
PHASES = {"QUEUED": "Starting", "PENDING": "Starting", "BLOCKED": "Starting", "WAITING_FOR_RETRY": "Starting",
          "RUNNING": "Running", "TERMINATING": "Running"}


def when(t, short=False):
    """A time as every page shows it: Oct 22, 2026, 14:05 UTC (t: a UTC datetime, or epoch
    milliseconds). short: Oct 22, 14:05, for feeds where the full time is the tooltip."""
    if isinstance(t, (int, float)):
        t = datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc)
    return f"{t:%b} {t.day}, {t:%H:%M}" if short else f"{t:%b} {t.day}, {t.year}, {t:%H:%M} UTC"


class RequestError(ValueError):
    """A request the user has to fix; the message is shown on the form."""


class BusinessUnitUnavailable(RequestError):
    """The person's chosen business unit cannot be read just now (the database does not answer).
    Never read as "none chosen": that would send them to choose one they cannot save."""

    def __init__(self):
        super().__init__("Your business unit can't be read just now. Try again in a minute.")


@dataclass
class Workspace:
    name: str
    bu: str
    host: str
    jobs: dict = field(default_factory=dict)   # kind -> {"id": ..., "tags": {...}}
    error: str = ""                            # why the app cannot use it, if it cannot


@dataclass
class Request:
    task: str
    workspace: str
    resource: str
    request_id: str
    started: str
    status: str            # In progress | Completed | Failed; for one that waits for a person: Pending approval | Reply needed | Rejected
    message: str = ""      # why it failed
    run_id: int = 0
    kind: str = ""
    link: str = None       # where to find what it made, once completed
    phase: str = ""        # Starting | Running | Done
    started_ms: int = 0
    running_ms: int = 0    # when the job began to run (after starting compute), if it has
    ended_ms: int = 0      # when it ended, if it has
    params: dict = field(default_factory=dict)

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if k != "params"}


def load_config(path):
    with open(path) as f:
        return json.load(f)


# Each kind of request, as the requester reads it.
APPROVAL_TYPES = {"personal_schema": "Personal schema", "project_schema": "Project schema", "team_schema": "Team schema",
                  "folder": "Workspace folder"}
# The states in which a request waits for a person (the database's request_status).
WAITING = ("submitted", "replied", "needs_info")


def record_params(row, w):
    """A request record's job parameters: what the requester asked for, and its request ID.
    w: its workspace (for the schema job's catalog), or None if the app no longer serves it."""
    if row["kind"] == "folder":
        params = {"folder": row["name"], "requested_by": row["requested_by"]}
    else:
        catalog = w.jobs["personal_schema"]["tags"].get("cd_catalog", "") if w and "personal_schema" in w.jobs else ""
        params = {"user": row["requested_by"], "catalog": catalog,
                  "schema": "" if row["kind"] == "personal_schema" else row["name"]}
    return {**params, "owner_group": row.get("owner_group") or "", "reason": row.get("reason") or "", "request_id": row["id"]}


def workspace_id_of(host, workspace_id=""):
    """The workspace ID for o= in links: the one Terraform gives, or the number in an Azure
    Databricks host (adb-<id>.<n>); "" for other hosts, which need none."""
    found = re.search(r"//adb-(\d+)\.", host)
    return str(workspace_id or (found[1] if found else ""))


def genie_one_link(host, prompt="", workspace_id=""):
    """Genie One's chat in a workspace, with a first question if one is given."""
    host = host.rstrip("/")
    wid = workspace_id_of(host, workspace_id)
    query = {**({"o": wid} if wid else {}), **({"q": prompt} if prompt else {})}
    return f"{host}/one/chat" + (f"?{urllib.parse.urlencode(query, quote_via=urllib.parse.quote)}" if query else "")


def fill(text, w):
    """{host}, {workspace_id} and {catalog} in a link or a prompt, from a workspace in config.json."""
    host = w["host"].rstrip("/")
    return (text.replace("{host}", host).replace("{workspace_id}", workspace_id_of(host, w.get("id")))
                .replace("{catalog}", w.get("catalog") or ""))


def new_request_id():
    return "ss-" + secrets.token_hex(4)


def schema_name(email, prefix="cd_"):
    """The personal schema's name: cd_ plus the email before the @ (as the job names it)."""
    return prefix + re.sub(r"[^a-z0-9]+", "_", email.split("@")[0].lower()).strip("_")


def check_schema(name, prefix):
    if not re.fullmatch(SCHEMA, name or "") or len(name) > 100:
        raise RequestError("The schema name must be lowercase letters, digits and underscores.")
    if prefix and name.startswith(prefix):
        raise RequestError(f"A custom schema can't start with {prefix}: that is how personal schemas are named.")


def check_reason(reason):
    """What it will be used for: one or two sentences, which an approver reads."""
    if len(reason) < 10:
        raise RequestError("Describe what it will be used for in a sentence or two.")
    if len(reason) > 1000:
        raise RequestError("Keep the description under 1000 characters.")


def check_folder(folder):
    if not re.fullmatch(FOLDER, folder or "") or folder in RESERVED_FOLDERS:
        raise RequestError("The folder name must be lowercase letters, digits and dashes "
                           f"(and not {', '.join(RESERVED_FOLDERS)}).")


def params_of(run):
    """A run's job parameters, as given or by default."""
    return {p.name: (p.value if p.value is not None else p.default) for p in run.job_parameters or []}


def requester(kind, params):
    """Who asked: the personal schema job calls them user, the team folder job requested_by."""
    return params.get("user") if kind == "personal_schema" else params.get("requested_by")


def folder_path(w, folder):
    """Where the team folder job of workspace w puts a folder: under its root (its cd_root tag)."""
    return f"{w.jobs['team_folder']['tags'].get('cd_root', '/Workspace').rstrip('/')}/{folder}"


def keep(cache, key, value, limit=2000):
    """Remember value under key; full, the cache forgets its oldest entries first."""
    cache.pop(key, None)
    cache[key] = (time.time(), value)
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def status_of(state):
    """In progress, Completed or Failed, from a run's state."""
    life = getattr(getattr(state, "life_cycle_state", None), "value", None) or ""
    result = getattr(getattr(state, "result_state", None), "value", None) or ""
    if life not in ("TERMINATED", "INTERNAL_ERROR", "SKIPPED"):
        return "In progress"
    return "Completed" if result == "SUCCESS" else "Failed"


def failure_reason(text):
    """The first line of a job's error: the job's own message (ValueError: ...), without the prefix."""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return re.sub(r"^\w+Error: ", "", line)[:300]


class Portal:
    """The portal for one user's requests, across the workspaces it serves.

    client(host) returns a Databricks WorkspaceClient for a workspace (signed in as the app's
    service principal); tests pass a fake.
    """

    def __init__(self, config, client, cache_seconds=300, run_cache_seconds=3, store=None, shown=None):
        self.config = config
        # config with the approvals app's Settings in it (settings.apply), read when a job runs.
        self.shown = shown or (lambda: self.config)
        self.client = client
        # The app's database (store.Store): the only list of requests. None only when config.json
        # has none (a misconfigured or local run): then nothing is sent, and the pages say why.
        self.store = store
        self._replies = {}   # user -> (when, how many requests wait for their reply)
        self.cache_seconds = cache_seconds
        self._workspaces, self._loaded = None, 0
        # Polled runs: several tabs or users polling share one Jobs API call per few seconds,
        # and a finished run (which never changes) is kept, so its output is read once.
        self.run_cache_seconds = run_cache_seconds
        self._runs = {}       # (workspace, run_id) -> (time read, Request or None)
        self._personal = {}   # (workspace, user) -> (time read, the personal schema card)
        self._checks = {}     # the request asked about -> (time, the AI check's result)
        self._statuses = {}   # (workspace, run_id) -> (time read, status), for the approvals app
        self._bus = {}        # person -> (time read, their business unit or None), for the BU lookup
        self._chosen = {}     # person -> (time read, the business unit they chose or None), without it
        self._toured = {}     # person -> (time read, True): had the guided tour, which stays so

    # ---- Workspaces and their jobs ----

    def workspaces(self):
        if self._workspaces is None or time.time() - self._loaded > self.cache_seconds:
            # Every workspace's job is in the hub (scripts/app_build.py jobs_target), tagged with the
            # workspace it serves: one listing, and no call to another workspace. host stays the
            # workspace's own, for the links people open in it.
            found = [Workspace(ws["name"], ws["bu"], ws["host"]) for ws in self.config["workspaces"]]
            by_name = {w.name: w for w in found}
            try:
                for job in self.hub().jobs.list():
                    tags = (job.settings.tags or {}) if job.settings else {}
                    w = by_name.get(tags.get("cd_workspace"))
                    if w and tags.get("cd_self_service") in TASKS:
                        w.jobs[tags["cd_self_service"]] = {"id": job.job_id, "tags": tags}
                for w in found:
                    if not w.jobs:
                        w.error = "no self-service job found in the hub for it (app_deploy.py deploys one per workspace)"
            except Exception as e:
                for w in found:
                    w.error = f"the hub's jobs cannot be read: {str(e).splitlines()[0][:200]}"
            self._workspaces, self._loaded = found, time.time()
        return self._workspaces

    def workspace(self, name, kind):
        for w in self.workspaces():
            if w.name == name and kind in w.jobs:
                return w
        raise RequestError("Choose a workspace this request is available in.")

    def available(self, kind):
        return [w for w in self.workspaces() if kind in w.jobs]

    # ---- The person's business unit: the lookup function (bu_lookup), or the one they chose ----

    NO_BU = "We couldn't find your business unit, so this request can't be sent. Contact your platform admin."

    def business_units(self):
        """The business units the app serves: each served workspace's prefix, upper case."""
        return sorted({w["bu"].upper() for w in self.config["workspaces"]})

    def chosen_bu(self, user):
        """The business unit the person chose (without a lookup function), if it is still one the
        app serves; None otherwise. Kept a minute: it changes only when they change it here."""
        if not hasattr(self.store, "chosen_business_unit") or self.config.get("bu_lookup"):
            return None
        cached = self._chosen.get(user)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        try:
            bu = self.store.chosen_business_unit(user)
        except Exception as e:   # not cached: the next page asks the database again
            warn(f"reading {user}'s business unit", e)
            raise BusinessUnitUnavailable() from e
        bu = bu if bu in self.business_units() else None
        keep(self._chosen, user, bu)
        return bu

    def choose_bu(self, user, bu):
        """Record the person's business unit. Only without a lookup function (it decides then)."""
        if self.config.get("bu_lookup"):
            raise RequestError("Your business unit comes from your organization's directory; it can't be changed here.")
        bu = (bu or "").strip().upper()
        if bu not in self.business_units():
            raise RequestError("Choose one of the business units listed.")
        self.store.choose_business_unit(user, bu)
        keep(self._chosen, user, bu)

    def needs_bu_choice(self, user):
        """Whether to ask the person for their business unit: no lookup function, several to
        choose from, and no choice yet."""
        return hasattr(self.store, "chosen_business_unit") and not self.config.get("bu_lookup") and len(self.business_units()) > 1 \
            and self.chosen_bu(user) is None

    def bu_of(self, user):
        """The person's business unit: from the lookup function (run on the host's warehouse as
        the app), or None when it does not know them, kept an hour (ten minutes for "not known");
        without one, the business unit they chose (or None). RequestError when the lookup cannot
        answer."""
        lookup = self.config.get("bu_lookup")
        if not lookup:
            return self.chosen_bu(user)
        cached = self._bus.get(user)
        if cached and time.time() - cached[0] < (3600 if cached[1] else 600):
            return cached[1]
        fn = ".".join(f"`{part}`" for part in lookup["function"].split("."))   # catalog.schema.function, checked by scripts/app_build.py
        try:
            out = self.client(lookup["host"]).api_client.do("POST", "/api/2.0/sql/statements", body={
                "warehouse_id": lookup["warehouse_id"], "statement": f"SELECT {fn}(:email)", "wait_timeout": "30s",
                "on_wait_timeout": "CANCEL", "parameters": [{"name": "email", "value": user, "type": "STRING"}]})
            if out.get("status", {}).get("state") != "SUCCEEDED":
                raise RuntimeError((out.get("status", {}).get("error") or {}).get("message") or out.get("status", {}).get("state"))
            rows = (out.get("result") or {}).get("data_array") or [[None]]
            bu = (rows[0][0] or "").strip().upper() or None
        except Exception as e:
            warn(f"looking up the business unit of {user}", e)
            raise RequestError("Your business unit can't be checked just now. Try again in a minute.") from e
        keep(self._bus, user, bu)
        return bu

    def workspaces_for(self, user, kind):
        """The workspaces a person's request of this kind may go to: with the BU lookup, only
        their own business unit's; otherwise every workspace that offers it. RequestError when
        the lookup does not know them, or their BU has none."""
        offered = self.available(kind)
        if not self.config.get("bu_lookup"):
            chosen = self.chosen_bu(user)   # the one they chose; until then, every workspace
            mine = [w for w in offered if w.bu.upper() == chosen] if chosen else offered
            if not mine:
                raise RequestError(f"Your business unit ({chosen}) has no workspace for this request yet. Choose another, or contact your platform admin.")
            return mine
        bu = self.bu_of(user)
        if bu is None:
            raise RequestError(self.NO_BU)
        mine = [w for w in offered if w.bu.upper() == bu]
        if not mine:
            raise RequestError(f"Your business unit ({bu}) has no workspace for this request yet. Contact your platform admin.")
        return mine

    def open_workspace(self, user, prompt, tour=False):
        """Genie One in the person's own workspace: the guided tour (with the onboarding prompt)
        the first time, or when they ask for it again (tour); plain Genie One after that, or when
        there is no prompt. None when there is no workspace for them."""
        if not prompt or (not tour and self.toured(user)):
            return self.genie_one(user)
        link = self.genie_one(user, prompt)
        if link and hasattr(self.store, "record_tour"):
            try:
                self.store.record_tour(user)
                keep(self._toured, user, True)
            except Exception as e:   # they get the tour again next time: better than none
                warn(f"recording {user}'s guided tour", e)
        return link

    def toured(self, user):
        """Whether the person has had the guided tour. Without a database, or when it cannot be
        read, not: the tour again is better than none."""
        if user in self._toured:
            return True
        if not hasattr(self.store, "toured"):
            return False
        try:
            done = self.store.toured(user)
        except Exception as e:
            warn(f"reading whether {user} had the guided tour", e)
            return False
        if done:
            keep(self._toured, user, True)
        return done

    def my_workspace(self, user):
        """The person's own workspace in config.json (their business unit's; the first one until
        they have one), or None when there is none for them."""
        mine = self.config["workspaces"]
        try:
            bu = self.bu_of(user)
        except RequestError:
            return None
        if bu or self.config.get("bu_lookup"):
            mine = [w for w in mine if w["bu"].upper() == bu]
        return mine[0] if mine else None

    def genie_one(self, user, prompt=""):
        """Genie One in the person's own workspace, with a first question if one is given (its
        {catalog} filled in); None when there is no workspace for them."""
        w = self.my_workspace(user)
        return genie_one_link(w["host"], fill(prompt, w), w.get("id")) if w else None

    def links_for(self, user, links):
        """The links with {host}, {workspace_id} and {catalog} of the person's own workspace, so
        Discover and the access requests open where their data is. A link that needs a
        workspace is left out (None) when they have none."""
        w = self.my_workspace(user)
        return {k: (fill(v, w) if w else None) if isinstance(v, str) and "{" in v else v for k, v in (links or {}).items()}

    def _check_bu(self, user, w, kind):
        """A request goes only to the person's own business unit's workspace (the forms offer
        no other; this refuses one sent anyway)."""
        if w.name not in {x.name for x in self.workspaces_for(user, kind)}:
            raise RequestError("Requests go to your own business unit's workspace. Choose that one.")

    # ---- The user's personal schema: one per workspace ----

    def personal_schema(self, ws_name, user):
        """Whether the user already has their personal schema in a workspace:
        {"exists": True / False / None (unknown), "name": catalog.schema, "link": ...}.

        Asks Unity Catalog (the app can see which schemas exist: BROWSE on the catalog, which
        the workspace baseline grants the apps). Where it cannot, the answer is unknown: the card shows
        neither 0/1 nor 1/1, and asking is harmless (the job keeps an existing schema)."""
        w = next((w for w in self.workspaces() if w.name == ws_name and "personal_schema" in w.jobs), None)
        if w is None or not re.fullmatch(EMAIL, user):
            return {"exists": None, "name": "", "link": None}
        tags = w.jobs["personal_schema"]["tags"]
        catalog, schema = tags.get("cd_catalog", ""), schema_name(user, tags.get("cd_prefix", "cd_"))
        key = (ws_name, user)
        cached = self._personal.get(key)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        pending = self.active_request(ws_name, user, "personal_schema", f"{catalog}.{schema}")
        if pending:   # asked for and not done yet: not cached, so the card follows the run
            return {"exists": "pending", "name": f"{catalog}.{schema}", "run_id": pending.run_id,
                    "workspace": ws_name, "link": None}
        try:
            self.hub().schemas.get(f"{catalog}.{schema}")
            exists = True
        except NotFound:
            exists = False
        except Exception as e:   # no BROWSE on the catalog: unknown
            warn(f"looking up {catalog}.{schema}", e)
            exists = None
        found = {"exists": exists, "name": f"{catalog}.{schema}", "link": f"{w.host}/explore/data/{catalog}/{schema}"}
        keep(self._personal, key, found)
        return found

    def hub(self):
        """The app's own workspace (the hub), where the AI calls run: the Validate check,
        the AI gateway for the summaries. Not the workspace a request goes to."""
        return self.client(None)

    # ---- The AI check of a name and reason (advice for the requester; it decides nothing) ----

    def ai_check(self, ws_name, kind, name, reason, owner_group="", user=None):
        """Rules first (exact, free), then one call to the AI model (none when it is off). Returns checks.check()'s result,
        with the rules' rows first. Cached for 10 minutes: asking again costs nothing. user: the
        person asking, so a name is only looked up in their own business unit's workspace."""
        kind_job = "team_folder" if kind == "folder" else "personal_schema"
        w = self.workspace(ws_name, kind_job)
        if user is not None:
            self._check_bu(user, w, kind_job)
        key = (ws_name, kind, name, reason, owner_group)
        cached = self._checks.get(key)
        if cached and time.time() - cached[0] < 600:
            return cached[1]
        c = self.hub()
        try:
            if kind == "folder":
                check_folder(name)
            else:
                check_schema(name, w.jobs[kind_job]["tags"].get("cd_prefix", "cd_"))
            check_reason(reason)
        except RequestError as e:   # a rule says no: no need to ask the AI
            return {"rows": [(False, str(e))], "error": ""}
        if kind == "folder":
            taken = self._exists(lambda: c.workspace.get_status(folder_path(w, name)))
        else:
            taken = self._exists(lambda: c.schemas.get(f"{w.jobs[kind_job]['tags'].get('cd_catalog', '')}.{name}"))
        # taken: True, False, or None when the lookup could not answer (then it says so: never "free" by default)
        noun = "folder" if kind == "folder" else "schema"
        rules = [{True: (False, f"The {noun} name is already taken (fine only if it is yours)"),
                  False: (True, f"The {noun} name is available"),
                  None: (False, f"Could not confirm the {noun} name is available")}[taken]]
        model = self.ai_model()
        if not model:   # no AI: the rules' rows only
            return {"rows": rules, "error": ""}
        result = checks.check(self.hub(), model, kind, name, reason, owner_group, ws_name)
        result = {**result, "rows": rules + result["rows"]}
        if not result["error"]:
            keep(self._checks, key, result, limit=500)
        return result

    @staticmethod
    def _exists(get):
        """True or False from a Unity Catalog or workspace lookup; None if it could not tell.
        Permission denied means it exists and is someone else's: taken."""
        try:
            get()
            return True
        except NotFound:
            return False
        except PermissionDenied:
            return True
        except Exception as e:
            warn("checking whether a name is taken", e)
            return None

    # ---- Requests ----

    def request_schema(self, ws_name, user, schema="", owner_group="", reason=""):
        """Run the personal schema job for the user: their personal schema; with a name, a
        project schema; with a name and owner_group (any Entra account group: membership is not
        checked), a team schema the group can manage too. Returns the run's ID."""
        if not re.fullmatch(EMAIL, user):
            raise RequestError("Your account has no email address the job can use.")
        w = self.workspace(ws_name, "personal_schema")
        self._check_bu(user, w, "personal_schema")
        job = w.jobs["personal_schema"]
        if schema:
            check_schema(schema, job["tags"].get("cd_prefix", "cd_"))
            check_reason(reason)   # a personal schema needs none: everyone may have one
        if owner_group and not schema:
            raise RequestError("A team schema needs a name.")
        if owner_group and not re.fullmatch(GROUP, owner_group):
            raise RequestError("The team's group must be an Entra ID group's name: letters, digits, spaces and . _ -.")
        catalog = job["tags"].get("cd_catalog", "")
        resource = f"{catalog}.{schema or schema_name(user, job['tags'].get('cd_prefix', 'cd_'))}"
        pending = self._one_at_a_time(ws_name, user, "personal_schema", resource)
        if pending:   # already asked for: show the one running
            return pending.run_id
        self._personal.pop((ws_name, user), None)
        return self._start(w, "personal_schema", user, schema or resource.split(".", 1)[1], owner_group, reason, {
            "user": user, "catalog": catalog, "schema": schema, "owner_group": owner_group, "reason": reason})

    def request_folder(self, ws_name, user, folder, reason=""):
        """Run the team folder job for the user's folder: they and the workspace's platform admins
        get Can manage (the job); they share it with others in Databricks once it exists. Returns
        the run's ID."""
        check_folder(folder)
        check_reason(reason)
        w = self.workspace(ws_name, "team_folder")
        self._check_bu(user, w, "team_folder")
        pending = self._one_at_a_time(ws_name, user, "team_folder", folder_path(w, folder))
        if pending:   # already asked for: show the one running
            return pending.run_id
        # The job still takes an owner group (its contract): none from the form.
        return self._start(w, "team_folder", user, folder, "", reason, {
            "folder": folder, "requested_by": user, "owner_group": "", "reason": reason})

    def needs_approval(self, kind):
        """Whether this kind of request (the database's kinds) waits for an approver before its
        job runs (app.yaml human_approval)."""
        return kind in self.config.get("human_approval", ())

    def _start(self, w, job_kind, user, name, owner_group, reason, params):
        """Record the request, then run its job, then link the run to it. Recording comes first,
        so every request that runs has a record: if the database cannot take it, nothing runs.
        Returns the run's ID; for a request an approver must approve first, nothing runs: it
        returns the request's ID (a string), and the approvals app runs the job once approved."""
        if not self.store:
            raise RequestError("The app's requests database is not set up, so nothing was sent. Tell a platform admin.")
        kind = store_module.db_kind(job_kind, params)
        if self.needs_approval(kind):
            waiting = next((r for r in self._requests_of(user) if (r["workspace"], r["kind"], r["name"]) == (w.name, kind, name)
                            and r["state"] in WAITING and not r["run_id"]), None)
            if waiting:   # already asked for: show the one waiting
                return waiting["id"]
        request_id = new_request_id()
        try:
            self.store.record_request({"id": request_id, "kind": kind, "workspace": w.name,
                                       "bu": w.bu, "requested_by": user, "name": name, "owner_group": owner_group,
                                       "reason": reason})
        except Exception as e:
            warn(f"recording request {request_id}", e)
            raise RequestError("Your request could not be recorded just now, so it was not sent. Try again in a minute.") from e
        if self.needs_approval(kind):
            self._summarize_later({"id": request_id, "kind": kind, "workspace": w.name, "bu": w.bu, "requested_by": user,
                                      "name": name, "owner_group": owner_group, "reason": reason})
            return request_id
        try:
            run_id = self.hub().jobs.run_now(w.jobs[job_kind]["id"], job_parameters={**params, **self.settings_for(job_kind), "request_id": request_id}).run_id
        except Exception as e:   # recorded as failed, and the person told so (not an error page)
            warn(f"starting the {job_kind} job for {request_id} in {w.name}", e)
            self._quietly(self.store.start_failed, request_id, "The job could not be started.")
            raise RequestError("Your request was recorded, but its job could not be started. Try again in a minute; "
                               "if it keeps failing, tell your platform admin.") from e
        self._quietly(self.store.run_started, request_id, w.name, run_id)
        return run_id

    def summarize(self, row):
        """The approver's summary of a request that has none yet (the approvals app, on opening
        it): written now, kept with the request. None when it is off or the model cannot answer."""
        model = self.ai_model()
        if not model:
            return None
        try:
            result = summary_module.summarize(self.hub(), model, row)
        except Exception as e:
            warn(f"writing the AI summary of {row['id']}", e)
            return None
        if self.store:
            self._quietly(self.store.summarized, row["id"], result)
        return result

    def _summarize_later(self, r):
        """The approver's summary (summary.py), written in the background so sending is not
        slowed down; the approvals app writes it when it opens a request that has none."""
        model = self.ai_model()
        if not (model and self.store):
            return
        def run():
            try:
                self.store.summarized(r["id"], summary_module.summarize(self.hub(), model, r))
            except Exception as e:
                warn(f"writing the AI summary of {r['id']}", e)
        threading.Thread(target=run, daemon=True).start()

    def _requests_of(self, user):
        try:
            return self.store.requests_of(user)
        except Exception as e:
            raise RequestError("Your requests cannot be read just now. Try again in a minute.") from e

    def replies_needed(self, user):
        """How many of the user's requests wait for their answer to an approver (the My requests
        badge). Cached for a minute per person; 0 without the database or when it cannot answer."""
        if not self.store:
            return 0
        cached = self._replies.get(user)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        try:
            n = sum(r["state"] == "needs_info" for r in self.store.requests_of(user))
        except Exception as e:
            warn("counting the requests that need a reply", e)
            n = 0
        self._replies[user] = (time.time(), n)
        return n

    def held(self, user, request_id):
        """One of the user's requests, with its conversation (approvers' questions and comments,
        their replies, the decision), or None if it is not theirs. The AI review's own notes
        are for approvers and are left out."""
        if not self.store:
            return None
        row = next((r for r in self._requests_of(user) if r["id"] == request_id), None)
        if row is None:
            return None
        events = [e for e in self.store.events_of(request_id) if e["type"] != "reviewed"]
        return {**row, "events": events, "needs_approval": row["kind"] in self.config.get("human_approval", ())}

    def reply(self, user, request_id, body):
        """The requester answers an approver's question: the request goes back to the approvers."""
        body = body.strip()
        if not 1 <= len(body) <= 2000:
            raise RequestError("Write your answer first (at most 2000 characters).")
        row = self.held(user, request_id)
        if row is None:
            raise RequestError("Not a request of yours.")
        if row["state"] != "needs_info":
            raise RequestError("Nobody is waiting for an answer on this request.")
        self.store.event(request_id, "replied", actor=user, role="requester", body=body)
        self._replies.pop(user, None)

    def ai_model(self):
        """The model every AI feature uses, as the Settings are now (app.yaml ai_model until an admin
        changes it); empty: no AI."""
        return (self.shown().get("ai") or {}).get("model") or ""

    def settings_for(self, job_kind):
        """What a job is told from the Settings, as they are when it runs: the schema job, the model
        that writes a new schema's comment (empty: the plain comment)."""
        return {"comment_model": self.ai_model()} if job_kind == "personal_schema" else {}

    def run_recorded(self, row):
        """Run the job of a request in the database, as it was asked, with its request ID: once
        an approver approved it (approvals app). Returns the run's ID."""
        kind = "team_folder" if row["kind"] == "folder" else "personal_schema"
        try:   # the workspace too: one that is gone, or has no job now, also marks the request failed
            w = self.workspace(row["workspace"], kind)
            run_id = self.hub().jobs.run_now(w.jobs[kind]["id"], job_parameters={**record_params(row, w), **self.settings_for(kind)}).run_id
        except Exception:
            if self.store:
                self._quietly(self.store.start_failed, row["id"], "The job could not be started.")
            raise
        if self.store:
            self._quietly(self.store.run_started, row["id"], w.name, run_id)
        return run_id

    @staticmethod
    def _quietly(write, *args):
        """A database write after the job has started: if it fails, the request still runs, and
        the outcome is recorded the next time the app sees the run."""
        try:
            write(*args)
        except Exception as e:
            warn(f"recording {getattr(write, '__name__', 'an event')} in the database", e)

    def running(self, ws_name, kind, resource):
        """Everyone's requests for this resource that are still running (active runs only)."""
        w = next((w for w in self.workspaces() if w.name == ws_name and kind in w.jobs), None)
        if w is None:
            return []
        runs = self.hub().jobs.list_runs(job_id=w.jobs[kind]["id"], active_only=True)
        return [r for r in (self.describe(w, kind, run, requester(kind, params_of(run)), details=False) for run in runs)
                if r and r.resource == resource]

    def active_request(self, ws_name, user, kind, resource):
        """The user's request for this resource that is still running, if any."""
        return next((r for r in self.running(ws_name, kind, resource) if requester(r.kind, r.params) == user), None)

    def _one_at_a_time(self, ws_name, user, kind, resource):
        """Requests run side by side, but one at a time for each folder or schema: the user's
        own request still running (to show it), or refused if someone else's is."""
        running = self.running(ws_name, kind, resource)
        mine = next((r for r in running if requester(r.kind, r.params) == user), None)
        if running and not mine:
            raise RequestError("Another request for this name is running right now. "
                               "Choose another name, or try again in a minute.")
        return mine

    def describe(self, w, kind, run, user, details=True):
        """A run of a self-service job as the user's Request, or None if it is not theirs.

        details: for a finished run, also read its output (the failure reason, or what it
        made and a link to it); one more call per run.
        """
        params = params_of(run)
        if requester(kind, params) != user:
            return None
        status = status_of(run.state)
        if kind == "personal_schema":
            prefix = w.jobs[kind]["tags"].get("cd_prefix", "cd_")
            catalog, schema = params.get("catalog", ""), params.get("schema") or schema_name(user, prefix)
            resource, link = f"{catalog}.{schema}", f"{w.host}/explore/data/{catalog}/{schema}"
        else:
            resource, link = folder_path(w, params.get("folder", "")), None
        message = ""
        if details and status != "In progress" and run.tasks:
            try:
                out = self.hub().jobs.get_run_output(run.tasks[0].run_id)
                if status == "Failed":
                    message = failure_reason(out.error) or failure_reason(run.state.state_message)
                elif kind == "team_folder" and out.notebook_output and out.notebook_output.result:
                    link = f"{w.host}/browse/folders/{json.loads(out.notebook_output.result)['object_id']}"
            except Exception:
                message = failure_reason(getattr(run.state, "state_message", "")) if status == "Failed" else ""
        life = getattr(getattr(run.state, "life_cycle_state", None), "value", "") or ""
        task = TASKS[kind]
        if kind == "personal_schema" and params.get("schema"):
            task = TEAM_SCHEMA if params.get("owner_group") else PROJECT_SCHEMA
        return Request(task, w.name, resource, params.get("request_id") or str(run.run_id),
                       when(run.start_time or 0),
                       status, message, run_id=run.run_id, kind=kind, link=link if status == "Completed" else None,
                       phase=PHASES.get(life, "Running" if status == "In progress" else "Done"),
                       started_ms=run.start_time or 0, params=params,
                       running_ms=(run.start_time + run.setup_duration) if run.start_time and getattr(run, "setup_duration", None) else 0,
                       ended_ms=getattr(run, "end_time", None) or 0)

    def run(self, ws_name, run_id, user):
        """One of the user's requests by its run, for the status page; None if not theirs."""
        key = (ws_name, int(run_id))
        cached = self._runs.get(key)
        if cached and (cached[1] is not None and cached[1].status != "In progress"
                       or time.time() - cached[0] < self.run_cache_seconds):
            r = cached[1]
        else:
            w = next((w for w in self.workspaces() if w.name == ws_name and not w.error), None)
            if w is None:
                return None
            try:
                run = self.hub().jobs.get_run(int(run_id))
            except NotFound:   # a run that does not exist (or no longer): not found, not an error page
                return None
            kind = next((k for k, j in w.jobs.items() if j["id"] == run.job_id), None)
            # Described for the requester; the cache keeps it and answers only them.
            r = self.describe(w, kind, run, requester(kind, params_of(run))) if kind else None
            keep(self._runs, key, r)
            if r and r.kind == "personal_schema" and r.status != "In progress":
                self._personal.pop((ws_name, requester(r.kind, r.params)), None)   # the card shows the result now
        return r if r is not None and requester(r.kind, r.params) == user else None

    def run_link(self, ws_name, kind, run_id):
        """Where an admin sees a request's job run in Databricks (the approvals app), or None: in
        the hub, where every workspace's job runs (not the workspace the request is for).
        kind: the database's (folder, or a schema kind)."""
        job_kind = "team_folder" if kind == "folder" else "personal_schema"
        w = next((w for w in self.workspaces() if w.name == ws_name and job_kind in w.jobs), None)
        hub = (self.config.get("hub_host") or "").rstrip("/")
        return f"{hub}/jobs/{w.jobs[job_kind]['id']}/runs/{int(run_id)}" if hub and w and run_id else None

    def run_status(self, ws_name, run_id):
        """A run's status (In progress, Completed, Failed), whoever asked: for the approvals app,
        whose approvers see every request in their business units. Finished when the Jobs API no
        longer has it; None if it cannot be read."""
        key = (ws_name, int(run_id))
        cached = self._statuses.get(key)   # a finished run never changes; one in progress is read again after a few seconds
        if cached and (cached[1] != "In progress" or time.time() - cached[0] < self.run_cache_seconds):
            return cached[1]
        w = next((w for w in self.workspaces() if w.name == ws_name and not w.error), None)
        if w is None:
            return None
        try:   # one call: the status only (the requester's own page reads the details)
            status = status_of(self.hub().jobs.get_run(int(run_id)).state)
        except Exception as e:
            if not (isinstance(e, NotFound) or "does not exist" in str(e).lower()):
                return None
            status = "Finished"   # the Jobs API no longer has it
        keep(self._statuses, key, status)
        return status

    def runs(self, ids, user, limit=20):
        """Several of the user's requests at once ("workspace/run_id" each), for the Requests page."""
        out = {}
        for i in list(ids)[:limit]:
            ws_name, _, run_id = i.rpartition("/")
            if ws_name and run_id.isdigit():
                r = self.run(ws_name, run_id, user)
                if r:
                    out[i] = r
        return out

    def requests(self, user):
        """The user's requests in every workspace, newest first, from the database: the only
        record of them. RequestError when it cannot be read: there is no other list to show."""
        if not self.store:
            raise RequestError("The app's requests database is not set up. Tell a platform admin.")
        try:
            return self._requests_from_store(user)
        except Exception as e:
            warn("reading requests from the database", e)
            raise RequestError("Your requests cannot be read just now. Try again in a minute.") from e

    def _requests_from_store(self, user):
        """Requests from the database; each one's status from its job run (the Jobs API, the
        source of truth), read side by side and cached once the run has ended."""
        by_name = {w.name: w for w in self.workspaces()}
        rows = self.store.requests_of(user)

        def status_of_row(row):
            w = by_name.get(row["workspace"])
            if row["run_id"] and w and not w.error:
                try:
                    live = self.run(row["workspace"], row["run_id"], user)
                    if live:
                        return live
                except Exception as e:
                    if isinstance(e, NotFound) or "does not exist" in str(e).lower():   # gone after about 60 days
                        return self._request_from_row(row, w, "Finished", "Run details have expired (the Jobs API keeps 60 days)")
                    return self._request_from_row(row, w, "Unknown", "Its status cannot be read right now")
            if row["state"] == "start_failed":
                return self._request_from_row(row, w, "Failed", row["state_body"] or "The job could not be started.")
            if row["state"] == "rejected":
                return self._request_from_row(row, w, "Rejected", row["state_body"] or "")
            if row["state"] == "needs_info":
                return self._request_from_row(row, w, "Reply needed", row["state_body"] or "")
            if row["state"] in ("submitted", "replied") and row["kind"] in self.config.get("human_approval", ()):
                return self._request_from_row(row, w, "Pending approval", "")
            return self._request_from_row(row, w, "In progress", "")

        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(status_of_row, rows))   # the database's order: newest request first

    def _request_from_row(self, row, w, status, message):
        kind = "team_folder" if row["kind"] == "folder" else "personal_schema"
        task = {"personal_schema": TASKS["personal_schema"], "project_schema": PROJECT_SCHEMA,
                "team_schema": TEAM_SCHEMA, "folder": TASKS["team_folder"]}[row["kind"]]
        params = record_params(row, w)
        if kind == "team_folder":
            resource = folder_path(w, row["name"]) if w and "team_folder" in w.jobs else row["name"]
        else:
            resource = f"{params['catalog']}.{row['name']}" if params["catalog"] else row["name"]
        started = row["created_at"]
        return Request(task, row["workspace"], resource, row["id"], when(started), status, message,
                       run_id=row["run_id"] or 0, kind=kind, phase="Starting" if status == "In progress" else "Done",
                       started_ms=int(started.timestamp() * 1000), params=params)
