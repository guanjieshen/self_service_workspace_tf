-- Two requests an approver makes by hand: a domain (kind domain) and a group added to a workspace
-- (kind workspace_group). And a request's details beyond its columns, as JSON: a permanent
-- schema's access request emails, a domain's parent, application ID and groups, a group's access
-- level. The status view lists its columns by name, to take the new one at the end.
-- destructive: drops and re-adds the kind check only, with every kind it allowed before; no data changes.

ALTER TABLE self_service.requests DROP CONSTRAINT requests_kind_check;
ALTER TABLE self_service.requests ADD CONSTRAINT requests_kind_check
    CHECK (kind IN ('personal_schema', 'project_schema', 'team_schema', 'temporary_schema',
                    'temporary_extension', 'temporary_conversion', 'folder', 'domain', 'workspace_group'));
ALTER TABLE self_service.requests ADD COLUMN details jsonb;

CREATE OR REPLACE VIEW self_service.request_status AS
SELECT r.id, r.kind, r.workspace, r.bu, r.requested_by, r.name, r.owner_group, r.reason, r.created_at,
       e.type AS state, e.at AS state_at, e.data AS state_data, r.days, r.details
FROM self_service.requests r
LEFT JOIN LATERAL (
    SELECT type, at, data FROM self_service.request_events
    WHERE request_id = r.id AND type <> 'commented' AND type <> 'reviewed'
    ORDER BY at DESC, id DESC LIMIT 1
) e ON true;
