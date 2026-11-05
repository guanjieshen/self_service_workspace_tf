# The request record check, shared by the self-service jobs' notebooks (scripts/app_build.py
# writes it into each: edit bundle/jobs/notebooks/request_record_check.py). With jobs.require_request_record
# on, a run must be one the self-service app recorded, for exactly these parameters, and, for
# the kinds that always need a person (app.yaml human_approval), one an approver approved. So
# nobody can run the job for someone else, or for a request no approver has passed, by calling
# it directly; the app's own checks are no longer the only ones. Off (requests_catalog empty):
# it checks nothing. Turning it off is the break-glass for an admin who must run a job by hand.
# The records are the app's Lakebase database, read through its Unity Catalog catalog.


def _rows(sql):
    return [r.asDict() if hasattr(r, "asDict") else dict(r) for r in spark.sql(sql).collect()]


def check_request_record(request_id, expected):
    """expected: the request's fields as the app recorded them (kind, workspace, requested_by,
    name, owner_group)."""
    if not requests_catalog:
        return
    if not request_id:
        raise ValueError("request_id is required: this job runs only for requests made in the Citizen Development app "
                         "(require_request_record)")
    table = f"`{requests_catalog}`.`self_service`"
    found = _rows(f"SELECT kind, workspace, requested_by, name, coalesce(owner_group, '') AS owner_group "
                  f"FROM {table}.`requests` WHERE id = '{request_id}'")
    if not found:
        raise ValueError(f"{request_id} is not a request the Citizen Development app recorded")
    wrong = sorted(k for k, v in expected.items() if found[0].get(k) != v)
    if wrong:
        raise ValueError(f"this run's {', '.join(wrong)} differ from what {request_id} asked for")
    if expected["kind"] not in human_approval:
        return
    decided = _rows(f"SELECT type FROM {table}.`request_events` WHERE request_id = '{request_id}' "
                    f"AND type IN ('approved', 'rejected') ORDER BY id")
    if [e["type"] for e in decided][:1] != ["approved"]:
        raise ValueError(f"{request_id} has not been approved by an approver: this kind of request always needs a person")
