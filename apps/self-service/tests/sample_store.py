"""Sample requests for the approvals app's tests: an in-memory store with LakebaseStore's methods,
at a fixed time so the sample ages do not drift. Tests only; the app reads its database.
"""
import copy
import datetime as dt
import itertools

NOW = dt.datetime(2026, 10, 21, 15, 0)   # the sample requests' "now" (MockStore only)
from approvals_store import TYPES  # noqa: E402,F401
_UNUSED_TYPES = {"personal_schema": "Personal schema", "project_schema": "Project schema", "team_schema": "Team schema", "folder": "Workspace folder"}
# The AI review's questions (checks.py), and what each answer means, as an approver reads them.
QUESTIONS = {
    "name": "Name", "work": "What the work is", "contents": "What it will hold", "audience": "Who will use it",
    "data": "Kind of data", "use": "What it is for", "instructions": "Instructions to the approver"}
ANSWERS = {
    ("name", "fits"): "Matches the reason", ("name", "generic"): "Too general", ("name", "junk"): "Does not describe its purpose",
    ("work", "named"): "Named", ("work", "none"): "Not said",
    ("contents", "named"): "Named", ("contents", "general"): "Only in general terms", ("contents", "none"): "Not said",
    ("audience", "self"): "The requester", ("audience", "team"): "A team", ("audience", "role"): "A role", ("audience", "none"): "Not said",
    ("data", "operational"): "Operational or aggregate", ("data", "people"): "About people (pay, performance, identifiers)",
    ("data", "customer_or_external"): "Customer personal data, or leaves the company",
    ("use", "analysis"): "Analysis, a report or a dashboard", ("use", "system_of_record"): "An official system of record",
    ("use", "live_operations"): "Changes live operational systems",
    ("instructions", "none"): "None", ("instructions", "present"): "Tries to instruct the approver",
}
SAFE = {"name": "fits", "work": "named", "contents": "named", "audience": "team", "data": "operational", "use": "analysis", "instructions": "none"}


def _ai(**unsafe):
    answers = {**SAFE, **unsafe}
    return [{"question": q, "choice": a, "label": QUESTIONS[q], "answer": ANSWERS[(q, a)], "ok": a == SAFE[q]} for q, a in answers.items()]


def _req(i, kind, name, ws, bu, who, reason, hours_ago, group=None, status="waiting", ai=None, rules=None, decision=None, talk=()):
    submitted = NOW - dt.timedelta(hours=hours_ago)
    decision = decision and {**decision, "outcome": status}
    r = {"id": f"ss-{i:04d}", "kind": kind, "type": TYPES[kind], "name": name, "workspace": ws, "bu": bu,
         "requested_by": who, "owner_group": group, "reason": reason, "submitted": submitted, "status": status,
         "rules": rules or [{"label": "Name is available", "ok": True}],
         "ai": ai if ai is not None else _ai(), "decision": decision, "summary": SUMMARIES.get(f"ss-{i:04d}")}
    # The conversation: every step, in order, append-only (the planned request_events table).
    flagged = [a["label"] for a in r["ai"] if not a["ok"]] + [x["label"] for x in r["rules"] if not x["ok"]]
    r["events"] = [{"at": submitted, "actor": who, "role": "requester", "type": "submitted", "body": reason},
                   {"at": submitted + dt.timedelta(seconds=1), "actor": "AI approval review", "role": "system", "type": "reviewed",
                    "body": "Manual review required" + (": " + ", ".join(flagged) if flagged else "")}]
    for hours, actor, role, kind_, body in talk:
        r["events"].append({"at": submitted + dt.timedelta(hours=hours), "actor": actor, "role": role, "type": kind_, "body": body})
    if decision:
        r["events"].append({"at": decision["at"], "actor": decision["by"], "role": "approver", "type": status, "body": decision["comment"]})
    return r


SUMMARIES = {
    "ss-0001": {"headline": "Project schema for pay equity analysis with salaries and SINs",
                "summary": "Ana asks for a schema to analyse pay equity across regions, loading employee salaries and social insurance numbers.",
                "concerns": [{"label": "Pay and SIN data", "level": "high", "detail": "Salaries and social insurance numbers are sensitive personal data."},
                             {"label": "Who can see it", "level": "medium", "detail": "It does not say who besides Ana will read the results."},
                             {"label": "Naming", "level": "low", "detail": "hr_pay_equity is clear, but not tied to a team."}],
                "questions": ["Do you need social insurance numbers, or would an employee ID do?"], "model": "system.ai.claude-sonnet-5-5"},
    "ss-0002": {"headline": "Team schema for weekly pipeline snapshots by region",
                "summary": "Sam asks for a team schema for sales-ops. The reason was vague; their reply says it holds weekly Salesforce pipeline snapshots by region, without customer contacts.",
                "concerns": [{"label": "Naming", "level": "low", "detail": "sales_data does not say what it holds."}],
                "questions": ["Could the schema be named for what it holds, for example sales_pipeline_snapshots?"], "model": "system.ai.claude-sonnet-5-5"},
    "ss-0004": {"headline": "Project schema to write SCADA setpoints for the north line pilot",
                "summary": "Raj asks for a schema to write new control setpoints back to SCADA for a pilot.",
                "concerns": [{"label": "Operational impact", "level": "high", "detail": "Writing setpoints to SCADA changes live control systems."}],
                "questions": ["Will anything write to SCADA directly, or does an operator apply the setpoints?"], "model": "system.ai.claude-sonnet-5-5"},
}

SAMPLE = [
    _req(1, "project_schema", "hr_pay_equity", "fin-citizen-dev", "FIN", "ana.lopez@contoso.com",
         "Load employee salaries and social insurance numbers to analyse pay equity across regions.", 3,
         ai=_ai(data="people")),
    _req(2, "team_schema", "sales_data", "sales-citizen-dev", "SALES", "sam.chen@contoso.com",
         "Some data for the team.", 26, group="sales-ops", ai=_ai(contents="general", audience="none", name="generic"),
         talk=[(4, "mo.ali@contoso.com", "approver", "needs_info", "What data will it hold, and is any of it about customers?"),
               (20, "sam.chen@contoso.com", "requester", "replied", "Weekly pipeline snapshots from Salesforce, by region. No customer contact details.")]),
    _req(3, "team_schema", "fin_exec_planning", "fin-citizen-dev", "FIN", "jo.martin@contoso.com",
         "Executive compensation planning documents for the next cycle.", 50, group="fin-exec-office", ai=_ai(data="people")),
    _req(4, "project_schema", "scada_setpoint_writeback", "plant-citizen-dev", "PLANT", "raj.patel@contoso.com",
         "Write new control setpoints back to SCADA for the north line pilot.", 7, ai=_ai(use="live_operations")),
    _req(5, "team_schema", "sales_contractor_hours", "sales-citizen-dev", "SALES", "lee.wong@contoso.com",
         "Contractor names, hours and rates to check invoices before payment.", 75, group="sales-finance-ops",
         ai=_ai(data="people")),
    _req(9, "project_schema", "fin_approver_tools", "fin-citizen-dev", "FIN", "dana.owner@contoso.com",
         "Tables the approvers use to review data access requests.", 5, ai=_ai(contents="general")),
    _req(6, "project_schema", "fin_month_end", "fin-citizen-dev", "FIN", "kim.park@contoso.com",
         "Month-end close checks for accounts payable.", 2,
         rules=[{"label": "Name is available", "ok": False, "note": "fin_month_end exists, owned by fin-controllers"}]),
    # Decided: for the history and the overview
    _req(7, "project_schema", "sales_customer_contacts", "sales-citizen-dev", "SALES", "ana.lopez@contoso.com",
         "Export customer names and phone numbers to send to a marketing agency.", 120, status="rejected",
         ai=_ai(data="customer_or_external"),
         decision={"by": "dana.owner@contoso.com", "at": NOW - dt.timedelta(hours=100), "comment": "Customer PII cannot leave the company. Use the aggregated campaign table instead."}),
    _req(8, "folder", "plant-reliability-models", "plant-citizen-dev", "PLANT", "raj.patel@contoso.com",
         "Models for equipment failure risk scoring, using inspection results.", 98, group="plant-reliability",
         ai=_ai(contents="general"), status="approved",
         decision={"by": "dana.owner@contoso.com", "at": NOW - dt.timedelta(hours=96), "comment": "Fine: the team confirmed it is inspection data only."}),
]
# The month's totals, for the overview, beyond the sample above.
AUTO_APPROVED_30D = 143
APPROVERS = {"FIN": ["dana.owner@contoso.com"], "SALES": ["dana.owner@contoso.com", "mo.ali@contoso.com"], "PLANT": ["dana.owner@contoso.com"]}


class MockStore:
    """Sample requests, in memory, for local design work: the same methods as LakebaseStore."""

    @staticmethod
    def now():
        return NOW

    def __init__(self):
        self._rows = {r["id"]: r for r in copy.deepcopy(SAMPLE)}
        self._ids = itertools.count(len(SAMPLE) + 1)
        self._settings = []

    def bus_for(self, approver):
        """The business units this person approves for."""
        return sorted(bu for bu, people in APPROVERS.items() if approver in people)

    def queue(self, approver, bu=None, kind=None):
        """Requests waiting for a person, in the approver's BUs, oldest first."""
        mine = set(self.bus_for(approver))
        rows = [r for r in self._rows.values() if r["status"] in ("waiting", "needs_info") and r["bu"] in mine
                and (not bu or r["bu"] == bu) and (not kind or r["kind"] == kind)]
        return sorted(rows, key=lambda r: r["submitted"])

    def all(self, approver):
        """Every request in the approver's BUs, as the inbox reads them."""
        mine = set(self.bus_for(approver))
        out = []
        for r in self._rows.values():
            if r["bu"] in mine:
                asked = [e["at"] for e in r["events"] if e["role"] == "requester"]
                out.append({**r, "needs_person": True, "waiting_since": max(asked or [r["submitted"]])})
        return out

    def history(self, approver):
        mine = set(self.bus_for(approver))
        rows = [r for r in self._rows.values() if r["status"] in ("approved", "rejected") and r["bu"] in mine]
        return sorted(rows, key=lambda r: r["decision"]["at"], reverse=True)

    def get(self, approver, request_id):
        return next((r for r in self.all(approver) if r["id"] == request_id), None)

    def decide(self, approver, request_id, outcome, comment=""):
        """Approve, reject, or ask for more information: a shared inbox, so any approver of the
        request's BU may (their own requests too), but the first decision wins."""
        r = self._rows.get(request_id)
        if r is None or r["bu"] not in self.bus_for(approver):
            raise PermissionError("Not a request you approve")
        if outcome not in ("approved", "rejected", "needs_info"):
            raise ValueError(outcome)
        if r.get("decision"):
            raise ValueError(f"Already {r['decision']['outcome']} by {r['decision']['by']}.")
        if outcome in ("rejected", "needs_info") and not comment.strip():
            raise ValueError("Say why, so the requester knows what to change.")
        at = dt.datetime.now()
        r["status"] = outcome
        if outcome != "needs_info":   # a question is not a decision: the request still waits for one
            r["decision"] = {"outcome": outcome, "by": approver, "at": at, "comment": comment.strip()}
        r["events"].append({"at": at, "actor": approver, "role": "approver", "type": outcome, "body": comment.strip()})
        return r

    def overview(self, approver, days=30, bu=""):
        """The last days in numbers, for the approver's BUs (or one of them)."""
        mine = {bu} & set(self.bus_for(approver)) if bu else set(self.bus_for(approver))
        rows = [r for r in self._rows.values() if r["bu"] in mine and (NOW - r["submitted"]).days < days]
        decided = [r for r in rows if r["status"] in ("approved", "rejected")]
        waiting = [r for r in rows if r["status"] in ("waiting", "needs_info")]
        reviewed = len(rows)
        oldest = max(((NOW - r["submitted"]).total_seconds() / 3600 for r in waiting), default=0)
        by_bu = {bu: {"waiting": sum(r["bu"] == bu for r in waiting), "decided": sum(r["bu"] == bu for r in decided)} for bu in sorted(mine)}
        # Agreement: of the requests the AI sent to a person, how many the person approved (the AI was too strict).
        approved_anyway = sum(r["status"] == "approved" for r in decided)
        auto = round(AUTO_APPROVED_30D * days / 30 * len(mine) / max(len(self.bus_for(approver)), 1))
        return {"total": auto + reviewed, "auto": auto, "manual": reviewed,
                "auto_rate": round(100 * auto / (auto + reviewed)) if auto + reviewed else 0,
                "waiting": len(waiting), "oldest_hours": round(oldest), "decided": len(decided),
                "approved_anyway": approved_anyway, "by_bu": by_bu}

    # ---- Settings (settings.py), in memory ----

    def settings(self):
        latest = {}
        for e in self._settings:
            latest[e["key"]] = e
        return latest

    def set_settings(self, changes, actor):
        for key, value in changes:
            self._settings.append({"key": key, "value": value, "by": actor, "at": dt.datetime.now()})

    def setting_history(self, limit=20, offset=0, keys=(), q="", q_keys=()):
        out, seen = [], {}
        for e in self._settings:
            out.append({**e, "previous": seen.get(e["key"], (None,))[0], "first": e["key"] not in seen})
            seen[e["key"]] = (e["value"],)
        q = q.strip().lower()
        hit = lambda e: not q or e["key"] in q_keys or any(q in (v or "").lower() for v in (e["value"], e["previous"], e["by"]))
        out = [e for e in out[::-1] if (not keys or e["key"] in keys) and hit(e)]
        return out[offset:offset + limit]


