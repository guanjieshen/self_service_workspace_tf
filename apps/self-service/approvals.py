"""The approvals app: the same code as the self-service app, deployed with APP_MODE=approvals.

Approvers (platform admins and BU data owners) work one shared inbox of the requests a person
decides (app.yaml human_approval: project and team schemas by default), in the BUs they
approve for: what was asked, why, and the AI summary (advice only; the requester never sees
it). They approve (which runs the job), reject, or ask for more information.

These routes exist only in approvals mode (register() is not called otherwise), so the
self-service deployment, which every employee can open, has no approval pages at all.
"""
import datetime as dt
import pathlib
from urllib.parse import urlencode

from fastapi import Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import approvals_store
import settings

OUTCOMES = {"approve": "approved", "reject": "rejected", "ask": "needs_info"}
# The inbox's tabs, in order: what each holds, and how it sorts by default.
VIEWS = {
    "review": ("Pending", "waiting"),          # waiting for an approver: longest waiting first
    "info": ("Waiting on requester", "waiting"),
    "decided": ("Approval history", "newest"),
    "all": ("All requests", "newest"),
}
PERIODS = (7, 30, 90)   # the Overview's presets, in days
SORTS = {"waiting": "Longest waiting", "newest": "Newest first", "oldest": "Oldest first"}
DONE = {"approved": "Approved: its job is running.", "rejected": "Rejected: the requester sees why.",
        "needs_info": "Question sent to the requester."}


def model_name(model):
    """A model as people read it: system.ai.claude-sonnet-5-5 -> Claude Sonnet 5.5."""
    import re
    m = re.fullmatch(r"(?:system\.ai\.)?claude-(\w+)-(\d+)-(\d+)", model or "")
    return f"Claude {m.group(1).title()} {m.group(2)}.{m.group(3)}" if m else (model or "an AI model")


def view_of(r):
    """Which tab a request belongs in (every request is also in All)."""
    if r.get("decision"):
        return "decided"
    if r["status"] == "needs_info":
        return "info"
    if r["status"] == "waiting" and r.get("needs_person", True):
        return "review"
    return None   # ran without a person (a personal schema, a folder): only in All


def inbox(rows, view, bu="", kind="", q="", sort=""):
    """The requests a tab shows, filtered and sorted, as (rows, sort used)."""
    sort = sort if sort in SORTS else VIEWS[view][1]
    words = q.lower().split()
    def matches(r):
        text = " ".join(str(r.get(k) or "") for k in ("id", "name", "requested_by", "owner_group", "reason", "type", "workspace")).lower()
        return all(w in text for w in words)
    out = [r for r in rows if (view == "all" or view_of(r) == view) and (not bu or r["bu"] == bu)
           and (not kind or r["kind"] == kind or approvals_store.TYPES.get(kind) == r["type"]) and matches(r)]
    if sort == "waiting":
        out.sort(key=lambda r: r.get("waiting_since") or r["submitted"])
    else:
        out.sort(key=lambda r: r["submitted"], reverse=sort == "newest")
    return out, sort


def day_label(day, today):
    if day == today:
        return "Today"
    if day == today - dt.timedelta(days=1):
        return "Yesterday"
    return day.strftime("%a, %b %d") if day.year == today.year else day.strftime("%a, %b %d, %Y")


def groups(rows, sort, now):
    """The rows under day headings when sorted by request day; one unnamed group otherwise."""
    if sort == "waiting":
        return [("", rows)]
    out = []
    for r in rows:
        label = day_label(r["submitted"].date(), now.date())
        if not out or out[-1][0] != label:
            out.append((label, []))
        out[-1][1].append(r)
    return out


def register(app, page, user_of, store, config=None):
    """The approvals pages, on the app's database (approvals_store.LakebaseStore; tests pass
    tests/sample_store.py's)."""
    config = config or {}

    # Only approvers can open this app, so when something fails they see what, instead of a
    # bare "Internal Server Error" (database and API errors carry no credentials).
    @app.exception_handler(Exception)
    async def show_error(request: Request, exc: Exception):
        import html
        import traceback
        where = traceback.extract_tb(exc.__traceback__)[-1]
        return HTMLResponse(status_code=500, content=(
            f'<!doctype html><link rel="stylesheet" href="/static/app.css?v={getattr(request.app.state, "asset_version", "")}"><main><div class="page-head">'
            "<h1>Something went wrong</h1><p class=\"lead\">The approvals app could not show this page.</p></div>"
            f'<div class="callout error" role="alert"><div class="callout-body"><p class="strong">{html.escape(type(exc).__name__)}</p>'
            f"<p class=\"mono\">{html.escape(str(exc))[:1500]}</p>"
            f"<p class=\"meta\">{html.escape(pathlib.Path(where.filename).name)}, line {where.lineno}, in {html.escape(where.name)}</p></div></div></main>"))

    def ctx(request, rows=None, **kw):
        user = user_of(request)
        rows = store.all(user) if rows is None else rows
        return {"mode": "approvals", "my_bus": store.bus_for(user), "view_of": view_of, "model_name": model_name,
                "waiting_count": sum(view_of(r) == "review" for r in rows), **kw}

    @app.get("/approvals", response_class=HTMLResponse)
    def queue(request: Request, view: str = "review", bu: str = "", kind: str = "", q: str = "", sort: str = "",
              done: str = "", outcome: str = ""):
        """One list of approvals: Pending (an approver's to approve or reject), Waiting on requester, Approval history, and
        All requests (monitoring and audit), each with search, filters and sorting in the URL."""
        user = user_of(request)
        view = view if view in VIEWS else "review"
        everything = store.all(user)
        rows, sort = inbox(everything, view, bu, kind, q, sort)
        counts = {v: sum(view_of(r) == v for r in everything) for v in VIEWS if v != "all"}
        counts["all"] = len(everything)
        filters = {k: v for k, v in {"bu": bu, "kind": kind, "q": q.strip()}.items() if v}
        query = urlencode({"view": view, **filters, **({"sort": sort} if sort != VIEWS[view][1] else {})})
        upnext = next((r for r in inbox(everything, "review", bu, kind, q)[0] if r["id"] != done), None)
        return page(request, "approvals/queue.html", nav="queue", **ctx(
            request, everything, groups=groups(rows, sort, store.now()), count=len(rows), view=view, views=VIEWS,
            counts=counts, sorts=SORTS, sort=sort, default_sort=VIEWS[view][1], bu=bu, kind=kind, q=q.strip(),
            filters=filters, query=query, types=approvals_store.TYPES, now=store.now(),
            notice=DONE.get(outcome) and {"id": done, "text": DONE[outcome]}, upnext=upnext))

    @app.get("/approvals/overview", response_class=HTMLResponse)
    def overview(request: Request, days: int = 30, bu: str = ""):
        """The figures for a period (PERIODS) and the approver's BUs, or one of them."""
        user = user_of(request)
        days = days if days in PERIODS else 30
        bu = bu if bu in store.bus_for(user) else ""
        return page(request, "approvals/overview.html", nav="overview", **ctx(
            request, o=store.overview(user, days=days, bu=bu), days=days, bu=bu, periods=PERIODS))

    tabs = {key: (label, titles) for key, label, titles in settings.TABS}

    @app.get("/approvals/settings", response_class=HTMLResponse)
    def settings_page(request: Request, tab: str = "", error: str = "", saved: str = "", form: dict = None):
        """The self-service app's links, banner and onboarding prompt (settings.py), one tab at a
        time: the defaults, which an approver may override here; every change is kept with who
        made it (the Change history tab)."""
        tab = tab if tab in tabs else settings.TABS[0][0]
        overrides = store.settings()
        return page(request, "approvals/settings.html", nav="settings", **ctx(
            request, tab=tab, tabs=settings.TABS, sections=[s for s in settings.SECTIONS if s[0] in tabs[tab][1]],
            values={**settings.values(config, overrides), **(form or {})}, defaults=settings.defaults(config),
            overrides={k: v for k, v in overrides.items() if v.get("value") is not None}, error=error, saved=saved == "1"))

    @app.get("/approvals/settings/history", response_class=HTMLResponse)
    def settings_history(request: Request, q: str = "", section: str = "", page_: int = Query(1, alias="page")):
        """Every change to the settings, newest first: searchable, by section, a page at a time."""
        per_page, page_ = 50, max(page_, 1)
        sections = {title: [key for key, _, _ in fields] for title, _, fields in settings.SECTIONS}
        section = section if section in sections else ""
        q_keys = [k for k, name in settings.NAMES.items() if q.strip() and q.strip().lower() in name.lower()]
        rows = store.setting_history(limit=per_page + 1, offset=(page_ - 1) * per_page, keys=sections.get(section, ()), q=q, q_keys=q_keys)
        filters = {k: v for k, v in {"q": q.strip(), "section": section}.items() if v}
        return page(request, "approvals/settings_history.html", nav="settings", **ctx(
            request, tab="history", tabs=settings.TABS, history=rows[:per_page], more=len(rows) > per_page, page_=page_, per_page=per_page, q=q.strip(),
            section=section, sections=list(sections), filters=filters, labels=settings.NAMES, defaults=settings.defaults(config)))

    @app.post("/approvals/settings")
    async def save_settings(request: Request):
        form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        tab = form.get("tab") if form.get("tab") in tabs else settings.TABS[0][0]   # back to the tab it came from
        try:
            if form.get("reset"):   # one setting back to app.yaml's value
                key = form["reset"]
                settings.check(key, "")
                changes = [(key, None)] if (store.settings().get(key) or {}).get("value") is not None else []
            else:
                changes = settings.changes(config, store.settings(), form)
        except ValueError as e:
            return settings_page(request, tab=tab, error=str(e), form={k: v for k, v in form.items() if k in settings.KINDS})
        if changes:
            store.set_settings(changes, user_of(request))
        return RedirectResponse(f"/approvals/settings?{urlencode({'tab': tab, **({'saved': 1} if changes else {})})}", status_code=303)

    @app.get("/approvals/{request_id}", response_class=HTMLResponse)
    def detail(request: Request, request_id: str, error: str = "", back: str = ""):
        r = store.get(user_of(request), request_id)
        if r is None:
            raise HTTPException(404, "Not a request you approve")
        return page(request, "approvals/detail.html", nav="queue", **ctx(
            request, r=r, error=error, now=store.now(), back=_safe(back)))

    def _safe(back):
        """The inbox view to return to (only a query string of this app's inbox)."""
        return back if back and not any(c in back for c in "/\\:") else ""

    @app.post("/approvals/{request_id}")
    def decide(request: Request, request_id: str, action: str = Form(""), comment: str = Form(""), back: str = Form("")):
        back = _safe(back)
        try:
            if action not in OUTCOMES:
                raise HTTPException(400)
            store.decide(user_of(request), request_id, OUTCOMES[action], comment)
        except PermissionError:
            raise HTTPException(404, "Not a request you approve")
        except ValueError as e:
            return detail(request, request_id, error=str(e), back=back)
        sep = "&" if back else ""
        return RedirectResponse(f"/approvals?{back}{sep}{urlencode({'done': request_id, 'outcome': OUTCOMES[action]})}", status_code=303)

    return store
