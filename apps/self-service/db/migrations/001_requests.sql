-- Requests and what happened to them: the only things no other system keeps.
-- Both tables are append-only: the apps INSERT and SELECT, never UPDATE or DELETE (grants.sql),
-- so history cannot be rewritten and two apps never fight over a row. A request's status is
-- derived from its events (request_status), never stored.

CREATE SCHEMA IF NOT EXISTS self_service;

CREATE TABLE self_service.requests (
    id           text PRIMARY KEY,                -- the request ID the job also gets (ss-…)
    kind         text NOT NULL CHECK (kind IN ('personal_schema', 'project_schema', 'team_schema', 'folder')),
    workspace    text NOT NULL,
    bu           text NOT NULL,
    requested_by text NOT NULL,
    name         text NOT NULL,                   -- the schema or folder asked for
    owner_group  text,                            -- a team schema's or folder's group
    reason       text,                            -- "Why do you need this?"
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX requests_by_person ON self_service.requests (requested_by, created_at DESC);
CREATE INDEX requests_by_bu ON self_service.requests (bu, created_at DESC);

CREATE TABLE self_service.request_events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id text NOT NULL REFERENCES self_service.requests (id),
    at         timestamptz NOT NULL DEFAULT now(),
    actor      text NOT NULL,                     -- an email, or the app ("AI approval review")
    role       text NOT NULL CHECK (role IN ('requester', 'approver', 'system')),
    type       text NOT NULL CHECK (type IN ('submitted', 'reviewed', 'needs_info', 'replied', 'commented',
                                             'approved', 'rejected', 'run_started', 'run_finished', 'withdrawn')),
    body       text,                              -- a comment or reply, if any
    data       jsonb NOT NULL DEFAULT '{}'        -- the AI's answers, the job run (workspace, run_id), its outcome
);
CREATE INDEX request_events_by_request ON self_service.request_events (request_id, at, id);
-- A shared inbox: the first decision wins, even if two approvers click at once.
CREATE UNIQUE INDEX one_decision_per_request ON self_service.request_events (request_id)
    WHERE type IN ('approved', 'rejected');
-- One job run per request.
CREATE UNIQUE INDEX one_run_per_request ON self_service.request_events (request_id)
    WHERE type = 'run_started';

-- Each request with its latest state-changing event (comments do not change the state).
CREATE VIEW self_service.request_status AS
SELECT r.*, e.type AS state, e.at AS state_at, e.data AS state_data
FROM self_service.requests r
LEFT JOIN LATERAL (
    SELECT type, at, data FROM self_service.request_events
    WHERE request_id = r.id AND type <> 'commented' AND type <> 'reviewed'
    ORDER BY at DESC, id DESC LIMIT 1
) e ON true;
