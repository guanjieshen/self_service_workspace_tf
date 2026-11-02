"""The self-service portal's web pages (FastAPI and Jinja templates). The logic is in portal.py.

Databricks Apps signs the user in and passes their email in X-Forwarded-Email; the app acts
as its own service principal. Locally: PORTAL_CONFIG=<config.json> PORTAL_USER=<email>
python main.py, signed in through the Databricks CLI.
"""
import functools
import logging
import os
import pathlib
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import cards
import portal

HERE = pathlib.Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")   # the app's log in Databricks Apps
# One codebase, two deployments: the self-service app (every employee) and, with
# APP_MODE=approvals, the approvals app (approvers only; its pages exist only in that mode).
CONFIG = portal.load_config(os.environ.get("PORTAL_CONFIG", HERE / "config.json"))
# The bundle deploys the same code twice; config.json says which app this is (APP_MODE for local runs).
MODE = os.environ.get("APP_MODE") or CONFIG.get("mode") or "self_service"


def ai_mode():
    """The AI check of a request's name and reason, on the forms (Validate): on or off. It
    coaches the requester; it never approves, refuses or routes anything. Read on each use, so
    tests can change it."""
    return "on" if CONFIG.get("ai_check") == "on" else "off"


def sent(workspace, started):
    """Where a request goes once sent: its run's status page, or, for one waiting for an
    approver (a request ID, not a run), its request page."""
    return RedirectResponse(f"/request/{started}" if isinstance(started, str) else f"/requests/{workspace}/{started}", status_code=303)


@functools.lru_cache(maxsize=None)
def client(host):
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(host=host)


import settings
import store

PORTAL = portal.Portal(CONFIG, client, store=store.Store.from_config(CONFIG))
# The links and banner approvers change in the approvals app (settings.py), over app.yaml's.
SETTINGS = settings.Cached(PORTAL.store.settings if PORTAL.store else dict)
app = FastAPI(title=CONFIG.get("title", "Self-Service"), docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
# The static files' version (their contents' hash): in their links, so browsers load new ones after a deploy.
import hashlib
def local_time(t, style="full"):
    """A time as a <time> element that app.js shows in the browser's own time zone and locale
    (the text here, UTC, is what shows without JavaScript). style: full, short (feeds), time
    or date (inbox cells), seconds (a request's steps). t: a UTC datetime (naive means UTC), or epoch milliseconds."""
    import datetime as dt
    from markupsafe import Markup, escape
    if isinstance(t, (int, float)):
        t = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    text = {"full": portal.when(t), "short": portal.when(t, short=True), "time": f"{t:%H:%M}", "seconds": f"{t:%H:%M:%S}", "date": f"{t:%b} {t.day}"}[style]
    return Markup(f'<time datetime="{t.isoformat()}" data-local="{style}" title="{escape(portal.when(t))}">{escape(text)}</time>')


templates.env.filters["local"] = local_time   # every time on every page: {{ t | local }}, {{ t | local("short") }}
templates.env.filters["pair"] = lambda v: (v, v)   # a select option whose value is its text


def mention(text, name):
    """The text, escaped, with each mention of name marked (the AI summary names what is asked for)."""
    from markupsafe import Markup, escape
    text, name = str(escape(text or "")), str(escape(name or ""))
    return Markup(text.replace(name, f'<span class="mention">{name}</span>') if name else text)


templates.env.filters["mention"] = mention
templates.env.globals["asset_version"] = app.state.asset_version = hashlib.sha1(b"".join((HERE / "static" / f).read_bytes() for f in ("app.css", "app.js"))).hexdigest()[:10]
# Databricks Apps sets DATABRICKS_APP_NAME. There, only its sign-in says who the user is.
LOCAL_USER = "" if os.environ.get("DATABRICKS_APP_NAME") else os.environ.get("PORTAL_USER", "")


def user_of(request):
    user = (request.headers.get("x-forwarded-email") or LOCAL_USER).strip().lower()
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


def page(request, template, **context):
    config = settings.apply(CONFIG, SETTINGS() if MODE != "approvals" else {})
    return templates.TemplateResponse(request, template, {
        "config": config, "links": config.get("links", {}), "user": user_of(request), "tasks": portal.TASKS,
        "approval": portal.approval_of(CONFIG), "approval_labels": portal.APPROVAL_LABELS, "mode": MODE, "ai_mode": ai_mode(),
        "replies_needed": PORTAL.replies_needed(user_of(request)) if MODE != "approvals" else 0, **context})


def offered(user, kind):
    """The workspaces this person's request may go to (their own business unit's, with the BU
    lookup), and why there are none, if so."""
    try:
        return PORTAL.workspaces_for(user, kind), ""
    except portal.RequestError as e:
        return [], str(e)


def personal_schema(user):
    """The user's personal schema in the first workspace that offers them (one per workspace):
    exists True, False, "pending" (asked for, still running) or None (unknown)."""
    workspaces, _ = offered(user, "personal_schema")
    return PORTAL.personal_schema(workspaces[0].name, user) if workspaces else {"exists": None}


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Whether this app works, checked as its own identity: its database answers, and it finds
    the self-service jobs. 503 if not. A deployment that "succeeded" only means the process
    started; this says whether it can do its job."""
    checks_ = {"database": "not set up (config.json has no database)"}
    if PORTAL.store:
        try:
            checks_["database"] = "ok" if PORTAL.store.ping() else "no answer"
        except Exception as e:
            checks_["database"] = f"{type(e).__name__}: {str(e)[:200]}"
    if CONFIG.get("bu_lookup") and MODE != "approvals":   # the lookup answers as the app (a missing grant shows here, not on a form)
        try:
            PORTAL._bus.pop("healthz@example.invalid", None)
            PORTAL.bu_of("healthz@example.invalid")
            checks_["bu_lookup"] = "ok"
        except portal.RequestError as e:
            checks_["bu_lookup"] = str(e.__cause__ or e)[:200]
    found = PORTAL.workspaces()
    checks_["workspaces"] = {w.name: w.error or f"{len(w.jobs)} self-service jobs" for w in found}
    ok = checks_["database"] == "ok" and checks_.get("bu_lookup", "ok") == "ok" and any(w.jobs for w in found)
    return JSONResponse({"ok": ok, "mode": MODE, **checks_}, status_code=200 if ok else 503)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse("/static/favicon-approvals.svg" if MODE == "approvals" else "/static/favicon.svg", status_code=301)


@app.get("/", response_class=HTMLResponse)
def catalog(request: Request):
    if MODE == "approvals":
        return RedirectResponse("/approvals", status_code=303)
    user = user_of(request)
    shown = settings.apply(CONFIG, SETTINGS())   # the links and the onboarding prompt, as admins set them
    return page(request, "catalog.html", nav="catalog", personal=personal_schema(user),
                groups=cards.groups(shown.get("links"), PORTAL.onboarding_link(user, shown["onboarding"]["prompt"])))


@app.get("/schema", response_class=HTMLResponse)
def schema_form(request: Request, error: str = ""):
    user = user_of(request)
    workspaces, why = offered(user, "personal_schema")
    return page(request, "schema.html", nav="catalog", workspaces=workspaces,
                schema=portal.schema_name(user), personal=personal_schema(user), error=error or why)


@app.post("/schema")
def schema_submit(request: Request, workspace: str = Form("")):
    try:
        started = PORTAL.request_schema(workspace, user_of(request))
    except portal.RequestError as e:
        return schema_form(request, error=str(e))
    return sent(workspace, started)


def team_groups(request, workspace):
    """The user's groups a team schema can go to: not the workspace's own (admins, users)."""
    return [g for g in groups_of(request, workspace) if g not in portal.WORKSPACE_GROUPS]


@app.get("/schema/custom", include_in_schema=False)
def custom_schema(request: Request):
    """Custom schemas are project schemas now; old links and bookmarks still work."""
    return RedirectResponse("/schema/project" + (f"?{request.url.query}" if request.url.query else ""), status_code=301)


@app.get("/schema/{kind}", response_class=HTMLResponse)
def named_schema_form(request: Request, kind: str, workspace: str = "", name: str = "", owner_group: str = "", reason: str = "", error: str = ""):
    """A project schema (the requester's) or a team schema (theirs and one of their groups')."""
    if kind not in ("project", "team"):
        raise HTTPException(404)
    workspaces, why = offered(user_of(request), "personal_schema")
    chosen = workspace if workspace in {w.name for w in workspaces} else (workspaces[0].name if workspaces else "")
    error = error or why
    return page(request, "schema_named.html", nav="catalog", team=kind == "team", workspaces=workspaces, chosen=chosen,
                my_groups=team_groups(request, chosen) if kind == "team" else [], name=name, owner_group=owner_group,
                reason=reason, error=error)


@app.post("/schema/{kind}")
def named_schema_submit(request: Request, kind: str, workspace: str = Form(""), name: str = Form(""), owner_group: str = Form(""),
                        reason: str = Form("")):
    if kind not in ("project", "team"):
        raise HTTPException(404)
    name, owner_group, reason = name.strip().lower(), owner_group.strip() if kind == "team" else "", reason.strip()
    try:
        if not name:
            raise portal.RequestError("Give the schema a name.")
        if kind == "team" and not owner_group:
            raise portal.RequestError("Choose the team (one of your groups) that manages the schema with you.")
        started = PORTAL.request_schema(workspace, user_of(request), schema=name, owner_group=owner_group,
                                        groups=team_groups(request, workspace) if owner_group else (), reason=reason)
    except portal.RequestError as e:
        return named_schema_form(request, kind, workspace=workspace, name=name, owner_group=owner_group, reason=reason, error=str(e))
    return sent(workspace, started)


def groups_of(request, workspace):
    """The signed-in user's groups, read with their own token (Databricks Apps forwards it)."""
    return PORTAL.groups_of(workspace, user_of(request), request.headers.get("x-forwarded-access-token")) if workspace else []


@app.get("/folder", response_class=HTMLResponse)
def folder_form(request: Request, workspace: str = "", error: str = "", form: dict = None):
    # Try again on a failed request opens the form with its values in the query string.
    form = form or {k: v for k, v in request.query_params.items() if k in ("folder", "owner_group", "reason")}
    workspaces, why = offered(user_of(request), "team_folder")
    chosen = workspace if workspace in {w.name for w in workspaces} else (workspaces[0].name if workspaces else "")
    error = error or why
    return page(request, "folder.html", nav="catalog", workspaces=workspaces, chosen=chosen,
                my_groups=groups_of(request, chosen), error=error, form=form)


@app.post("/folder")
async def folder_submit(request: Request):
    form = dict(await request.form())
    try:
        workspace = form.get("workspace", "")
        started = PORTAL.request_folder(workspace, user_of(request), form.get("folder", "").strip(),
                                        form.get("owner_group", "").strip(), groups_of(request, workspace),
                                        reason=form.get("reason", "").strip())
    except portal.RequestError as e:
        return folder_form(request, workspace=form.get("workspace", ""), error=str(e), form=form)
    return sent(workspace, started)


@app.get("/persona", response_class=HTMLResponse)
def persona(request: Request):
    """The personas, each with where to ask for it (links.persona_request)."""
    return page(request, "persona.html", nav="catalog")


@app.get("/ask", response_class=HTMLResponse)
def ask(request: Request):
    """Ask a question: Genie One in the person's own workspace. Without one for them (the BU
    lookup does not know them), the page says where to go instead."""
    link = PORTAL.genie_one(user_of(request))
    return RedirectResponse(link, status_code=303) if link else page(request, "ask.html", nav="catalog")


@app.get("/warehouses", response_class=HTMLResponse)
def warehouses(request: Request):
    return page(request, "warehouses.html", nav="catalog")


@app.get("/requests", response_class=HTMLResponse)
def requests(request: Request):
    try:
        items, error = PORTAL.requests(user_of(request)), ""
    except portal.RequestError as e:
        items, error = [], str(e)
    # Each status's tab; the ones only an approval request can have show only when there is one.
    counts = {s: sum(1 for r in items if r.status == s) for s in ("Reply needed", "Pending approval", "In progress", "Completed", "Failed", "Rejected")}
    counts = {s: n for s, n in counts.items() if n or s in ("In progress", "Completed", "Failed")}
    unavailable = [w for w in PORTAL.workspaces() if w.error]
    return page(request, "requests.html", nav="requests", items=items, counts=counts, unavailable=unavailable, error=error)


def check_kind(r):
    """Which form a request came from: None for a personal schema."""
    if r.kind == "team_folder":
        return "folder"
    if r.params.get("schema"):
        return "team_schema" if r.params.get("owner_group") else "project_schema"
    return None


@app.post("/api/check")
async def ai_check(request: Request):
    """Validate on a form: the rules and the AI check of the name and reason. Advice only:
    it changes nothing, and the form can be sent either way."""
    user_of(request)
    if ai_mode() == "off":
        raise HTTPException(404)
    f = dict(await request.form())
    kind = f.get("kind", "")
    if kind not in ("project_schema", "team_schema", "folder"):
        raise HTTPException(400)
    name = ((f.get("folder") if kind == "folder" else f.get("name")) or "").strip().lower()
    try:
        result = PORTAL.ai_check(f.get("workspace", ""), kind, name, (f.get("reason") or "").strip(),
                                 (f.get("owner_group") or "").strip() if kind != "project_schema" else "", user=user_of(request))
    except portal.RequestError as e:
        result = {"rows": [(False, str(e))], "error": ""}
    return JSONResponse({"rows": [{"ok": ok, "text": text} for ok, text in result["rows"]],
                         "error": result["error"]})


def retry_link(r):
    """The form again, filled in with a failed request's values."""
    if r.kind == "team_folder":
        return "/folder?" + urlencode({"workspace": r.workspace, "folder": r.params.get("folder", ""),
                                       "owner_group": r.params.get("owner_group", ""), "reason": r.params.get("reason", "")})
    if r.params.get("owner_group"):
        return "/schema/team?" + urlencode({"workspace": r.workspace, "name": r.params.get("schema", ""),
                                            "owner_group": r.params["owner_group"], "reason": r.params.get("reason", "")})
    if r.params.get("schema"):
        return "/schema/project?" + urlencode({"workspace": r.workspace, "name": r.params["schema"],
                                               "reason": r.params.get("reason", "")})
    return "/schema"


@app.get("/requests/{workspace}/{run_id}", response_class=HTMLResponse)
def request_status(request: Request, workspace: str, run_id: int):
    r = PORTAL.run(workspace, run_id, user_of(request))
    if r is None:
        raise HTTPException(404, "No such request of yours")
    kind = check_kind(r)
    # Whether a person approved it (its kind needs one: it ran, so one did); None for a personal schema.
    needs_approval = None if kind is None else portal.approval_of(CONFIG).get(kind) == "required"
    approver, events = None, []
    if needs_approval:   # who approved it, and the conversation with the approver, from the request's history
        try:
            held = PORTAL.held(user_of(request), r.request_id)
            events = [e for e in (held or {}).get("events", []) if e["type"] != "reviewed"]
            approver = next((e["actor"] for e in events if e["type"] == "approved"), None)
        except portal.RequestError:
            pass
    return page(request, "request.html", nav="requests", r=r, retry=retry_link(r), needs_approval=needs_approval, approver=approver, events=events)


@app.get("/request/{request_id}", response_class=HTMLResponse)
def held_request(request: Request, request_id: str, error: str = ""):
    """A request by its ID: one that waits for an approver (or was decided) has no run to show
    yet; once its job runs, its run's status page takes over."""
    try:
        r = PORTAL.held(user_of(request), request_id)
    except portal.RequestError as e:
        raise HTTPException(503, str(e))
    if r is None:
        raise HTTPException(404, "No such request of yours")
    if r["run_id"]:
        return RedirectResponse(f"/requests/{r['workspace']}/{r['run_id']}", status_code=303)
    return page(request, "request_held.html", nav="requests", r=r, error=error, label=portal.APPROVAL_TYPES.get(r["kind"], r["kind"]))


@app.post("/request/{request_id}/reply")
def reply(request: Request, request_id: str, body: str = Form("")):
    try:
        PORTAL.reply(user_of(request), request_id, body)
    except portal.RequestError as e:
        return held_request(request, request_id, error=str(e))
    return RedirectResponse(f"/request/{request_id}", status_code=303)


@app.get("/api/requests/{workspace}/{run_id}")
def request_status_api(request: Request, workspace: str, run_id: int):
    """The status page polls this until the request is done. Only the user's own requests."""
    r = PORTAL.run(workspace, run_id, user_of(request))
    if r is None:
        raise HTTPException(404, "No such request of yours")
    return JSONResponse({**r.as_dict(), "retry": retry_link(r) if r.status == "Failed" else None})


@app.get("/api/requests")
def requests_status_api(request: Request, ids: str = ""):
    """The Requests page polls its in-progress cards with one call: ids=ws/run_id,ws/run_id."""
    found = PORTAL.runs([i for i in ids.split(",") if i], user_of(request))
    return JSONResponse({i: {**r.as_dict(), "retry": retry_link(r) if r.status == "Failed" else None} for i, r in found.items()})


if MODE == "approvals":
    import approvals
    import approvals_store
    APPROVALS = approvals.register(app, page, user_of, store=approvals_store.LakebaseStore(
        PORTAL.store, {w["bu"] for w in CONFIG.get("workspaces", [])}, PORTAL.run_status, start=PORTAL.run_recorded,
        human_approval=CONFIG.get("human_approval", ()), summarize=PORTAL.summarize, run_link=PORTAL.run_link), config=CONFIG)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))
