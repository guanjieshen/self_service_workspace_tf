-- A temporary schema: a person's short-term schema (<prefix>tmp_<name>, tagged cd_expires), one at
-- a time. A new kind of request, so the kind check takes it.
-- destructive: drops and re-adds the kind check only, with every kind it allowed before; no data changes.

ALTER TABLE self_service.requests DROP CONSTRAINT requests_kind_check;
ALTER TABLE self_service.requests ADD CONSTRAINT requests_kind_check
    CHECK (kind IN ('personal_schema', 'project_schema', 'team_schema', 'temporary_schema', 'folder'));
