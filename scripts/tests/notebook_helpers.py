"""Helpers for the self-service job notebooks' tests (standard library only)."""
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent


def render_notebook(template, values):
    """Fill in a job notebook the way the build does (scripts/app_build.py)."""
    import sys
    sys.path.insert(0, str(SCRIPTS))
    import app_build as build
    return build.render(template, values)


class RecordsSpark:
    """spark.sql for the request record check: the app's records, by request ID.
    records: {request_id: (request fields, [(event type, data)])}."""

    def __init__(self, records, then=None):
        self.records, self.then = records, then   # then: the notebook's own spark.sql, for everything else

    def sql(self, text, args=None):
        import re
        import types
        m = re.search(r"(?:WHERE id|WHERE request_id) = '([^']*)'", text)
        if "`self_service`.`requests`" in text:
            rows = [self.records[m.group(1)][0]] if m and m.group(1) in self.records else []
        elif "`self_service`.`request_events`" in text:
            rows = [{"type": t, "data": d} for t, d in self.records.get(m.group(1), ({}, []))[1]
                    if f"'{t}'" in text] if m else []   # only the event types asked for
        else:
            return self.then(text, args) if args else self.then(text)
        rows = [types.SimpleNamespace(asDict=lambda r=r: dict(r)) for r in rows]
        return types.SimpleNamespace(collect=lambda: rows, count=lambda: len(rows))
