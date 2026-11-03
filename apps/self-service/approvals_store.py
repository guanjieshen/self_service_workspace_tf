"""The approvals app's data: requests that need a person, every request, and what was decided,
read from the app's database (LakebaseStore). Tests use tests/sample_store.py instead.
"""
import datetime as dt

# Every kind of request, as approvers read it (the database's kinds).
TYPES = {"personal_schema": "Personal schema", "project_schema": "Project schema", "team_schema": "Team schema", "folder": "Workspace folder"}
WAITING = ("submitted", "replied", "needs_info")   # states in which a request that needs a person waits


class LakebaseStore:
    """The approvals app's data, from the requests database (store.Store). A request's run
    status comes from its job run (run_status: the Jobs API), never from a copy."""

    def __init__(self, db, bus, run_status=None, start=None, human_approval=(), summarize=None, run_link=None):
        """start(row): runs an approved request's job (portal.Portal.run_recorded). human_approval:
        the kinds a person must always approve (app.yaml); they wait here instead of running.
        summarize(row): writes the AI summary of a request that has none (portal.Portal.summarize)."""
        self.db, self._bus = db, sorted(bus)
        self.run_status = run_status or (lambda workspace, run_id: None)
        self.run_link = run_link or (lambda workspace, kind, run_id: None)   # the run in Databricks (portal.Portal.run_link)
        self.start = start
        self.human_approval = set(human_approval)
        self.summarize = summarize

    @staticmethod
    def now():
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)   # submitted times are UTC, without a zone

    def bus_for(self, approver):
        # For now every approver approves for every BU the app serves: the app opens only for
        # one approvers group (approvals_group in hub.yaml; workspace admins by default). When BU data owners approve,
        # this maps the person's groups to their BUs, and queue/all/get filter by them.
        return self._bus

    def _record(self, row, events=None):
        status = self._status(row)
        d = row.get("decision")
        return {"id": row["id"], "kind": "folder" if row["kind"] == "folder" else "schema", "type": TYPES[row["kind"]],
                "name": row["name"], "workspace": row["workspace"], "bu": row["bu"], "requested_by": row["requested_by"],
                "owner_group": row["owner_group"], "reason": row["reason"] or "", "submitted": row["created_at"].replace(tzinfo=None),
                "status": status,
                "run": row["run"], "run_url": self.run_link(row["workspace"], row["kind"], (row["run"] or {}).get("run_id")),
                "decision": d and {**d, "at": d["at"].replace(tzinfo=None)},
                "needs_person": self.needs_person(row), "summary": row.get("summary"),
                "waiting_since": (row["state_at"] if row["state"] in ("submitted", "replied") else row["created_at"]).replace(tzinfo=None),
                "events": [{**e, "at": e["at"].replace(tzinfo=None)} for e in (events or [])]}

    def _status(self, row):
        """waiting | needs_info | approved | rejected | running | completed | failed | finished | unknown."""
        if row["state"] == "run_started" and row["run"].get("run_id"):
            live = self.run_status(row["workspace"], row["run"]["run_id"])
            return {"In progress": "running", "Completed": "completed", "Failed": "failed", "Finished": "finished"}.get(live, "unknown")
        if row["state"] == "start_failed":
            return "failed"
        if row["state"] in ("approved", "rejected", "needs_info"):
            return row["state"]
        return "waiting"

    def needs_person(self, row):
        """A request a person decides: its kind needs one (human_approval), and no job has run for it."""
        return not row["run"] and row["kind"] in self.human_approval

    def needs_review(self, row):
        """A request waiting for a person, undecided."""
        return row["state"] in WAITING and self.needs_person(row) and not row.get("decision")

    def queue(self, approver, bu=None, kind=None):
        rows = [r for r in self.db.requests_in([bu] if bu else self._bus) if self.needs_review(r)]
        out = [self._record(r) for r in rows if not kind or r["kind"] == kind]
        return sorted(out, key=lambda r: r["submitted"])

    def all(self, approver, bu=None, kind=None):
        rows = self.db.requests_in([bu] if bu else self._bus, limit=1000)
        return [self._record(r) for r in rows if not kind or r["kind"] == kind]

    def history(self, approver):
        return [r for r in self.all(approver) if r["status"] in ("approved", "rejected")]

    def get(self, approver, request_id):
        row = self._row(request_id)
        if row is None:
            return None
        if not row.get("summary") and self.summarize and self.needs_person(row):
            row = {**row, "summary": self.summarize(row)}   # sent before summaries, or not written yet
        return self._record(row, self.db.events_of(request_id))

    def _row(self, request_id):
        return next((r for r in self.db.requests_in(self._bus, limit=1000) if r["id"] == request_id), None)

    def decide(self, approver, request_id, outcome, comment=""):
        """Approve (and run its job), reject, or ask for more information. A shared inbox: any
        approver of the request's BU may (their own requests too: opening this app is the
        permission), and the first decision wins (the database keeps one)."""
        row = self._row(request_id)
        if row is None:
            raise PermissionError("Not a request you approve")
        if outcome not in ("approved", "rejected", "needs_info"):
            raise ValueError(outcome)
        if row.get("decision"):
            raise ValueError(f"Already {row['decision']['outcome']} by {row['decision']['by']}.")
        if not self.needs_person(row) or row["state"] not in WAITING:
            raise ValueError("This request is not waiting for a decision.")
        if outcome in ("rejected", "needs_info") and not comment.strip():
            raise ValueError("Say why, so the requester knows what to change.")
        if not self.db.decide(request_id, approver, outcome, comment.strip()):
            raise ValueError("Another approver decided first. Reload to see their decision.")
        if outcome == "approved":
            try:
                self.start(row)
            except Exception as e:
                raise ValueError("Approved, but its job could not be started. It shows as Failed; "
                                 "the requester can ask again.") from e
        return self._record(self._row(request_id))

    def overview(self, approver, days=30, bu=""):
        bus = [bu] if bu in self._bus else self._bus
        rows = self.db.requests_in(bus, limit=5000)
        recent = [r for r in rows if (dt.datetime.now(dt.timezone.utc) - r["created_at"]).days < days]
        waiting = [r for r in recent if self.needs_review(r)]
        auto = [r for r in recent if r["run"] and not r.get("decision")]
        oldest = max(((dt.datetime.now(dt.timezone.utc) - r["created_at"]).total_seconds() / 3600 for r in waiting), default=0)
        decided = [r for r in recent if r.get("decision")]
        by_bu = {b: {"waiting": sum(r["bu"] == b for r in waiting), "decided": sum(r["bu"] == b for r in decided)} for b in bus}
        total = len(recent)
        return {"total": total, "auto": len(auto), "manual": total - len(auto), "auto_rate": round(100 * len(auto) / total) if total else 0,
                "waiting": len(waiting), "oldest_hours": round(oldest), "decided": len(decided),
                "approved_anyway": sum(r["decision"]["outcome"] == "approved" for r in decided), "by_bu": by_bu}

    # ---- Settings (settings.py) ----

    def settings(self):
        return self.db.settings()

    def set_settings(self, changes, actor):
        self.db.set_settings(changes, actor)

    def setting_history(self, limit=20, offset=0, keys=(), q="", q_keys=()):
        return self.db.setting_history(limit, offset, keys, q, q_keys)
