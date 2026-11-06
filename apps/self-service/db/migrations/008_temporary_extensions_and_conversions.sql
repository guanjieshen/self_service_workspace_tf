-- Two requests about a temporary schema the person already has, each decided by an approver:
-- more time (temporary_extension: days, 7 for now, added to its cd_expires tag) and keeping it as a
-- project schema (temporary_conversion: relabelled in place). The days are the request's own, so
-- they are a column; the status view lists its columns by name, to take the new one at the end.
-- destructive: drops and re-adds the kind check only, with every kind it allowed before; no data changes.

ALTER TABLE self_service.requests DROP CONSTRAINT requests_kind_check;
ALTER TABLE self_service.requests ADD CONSTRAINT requests_kind_check
    CHECK (kind IN ('personal_schema', 'project_schema', 'team_schema', 'temporary_schema',
                    'temporary_extension', 'temporary_conversion', 'folder'));
ALTER TABLE self_service.requests ADD COLUMN days integer CHECK (days IS NULL OR days > 0);

CREATE OR REPLACE VIEW self_service.request_status AS
SELECT r.id, r.kind, r.workspace, r.bu, r.requested_by, r.name, r.owner_group, r.reason, r.created_at,
       e.type AS state, e.at AS state_at, e.data AS state_data, r.days
FROM self_service.requests r
LEFT JOIN LATERAL (
    SELECT type, at, data FROM self_service.request_events
    WHERE request_id = r.id AND type <> 'commented' AND type <> 'reviewed'
    ORDER BY at DESC, id DESC LIMIT 1
) e ON true;
