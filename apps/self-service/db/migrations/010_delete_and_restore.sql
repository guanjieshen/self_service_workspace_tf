-- Two requests that run straight away: deleting a schema now, with everything in it (kind
-- schema_delete: a temporary or permanent one, by its requester; a temporary one by an approver),
-- and giving a schema back the grants it got when it was made (kind schema_restore, for someone
-- who removed their own).
-- destructive: drops and re-adds the kind check only, with every kind it allowed before; no data changes.

ALTER TABLE self_service.requests DROP CONSTRAINT requests_kind_check;
ALTER TABLE self_service.requests ADD CONSTRAINT requests_kind_check
    CHECK (kind IN ('personal_schema', 'project_schema', 'team_schema', 'temporary_schema',
                    'temporary_extension', 'temporary_conversion', 'folder', 'domain', 'workspace_group',
                    'schema_delete', 'schema_restore'));
