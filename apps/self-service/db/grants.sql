-- Who may do what, re-applied on every apply (migrate.py), so a new app's role is granted as
-- soon as it exists. {self_service} and {approvals} are the apps' Postgres roles, {readers}
-- the people who may read it (each line runs once per reader); a line whose role is not given
-- is skipped. Append-only for the apps: SELECT and INSERT, never UPDATE or DELETE.
GRANT USAGE ON SCHEMA self_service TO {self_service};
GRANT SELECT, INSERT ON self_service.requests, self_service.request_events TO {self_service};
GRANT SELECT ON self_service.request_status TO {self_service};
-- Settings: the self-service app reads them; the approvals app (its Settings page) changes them.
GRANT SELECT ON self_service.settings TO {self_service};
-- The business unit people chose (without a lookup function): the self-service app records it.
GRANT SELECT, INSERT ON self_service.business_unit_choices TO {self_service};
GRANT SELECT ON self_service.chosen_business_units TO {self_service};
-- Who has had the guided tour (the Open Databricks Genie One card): the self-service app records it.
GRANT SELECT, INSERT ON self_service.guided_tours TO {self_service};
GRANT USAGE ON SCHEMA self_service TO {approvals};
GRANT SELECT ON self_service.requests, self_service.request_status TO {approvals};
GRANT SELECT, INSERT ON self_service.request_events TO {approvals};
GRANT SELECT, INSERT ON self_service.setting_events TO {approvals};
GRANT SELECT ON self_service.settings TO {approvals};
-- People who may look at the data (database.readers in app.yaml), for example in Lakebase's
-- Tables page or SQL editor: read only.
GRANT USAGE ON SCHEMA self_service TO {readers};
GRANT SELECT ON self_service.requests, self_service.request_events, self_service.request_status TO {readers};
GRANT SELECT ON self_service.setting_events, self_service.settings TO {readers};
GRANT SELECT ON self_service.business_unit_choices, self_service.chosen_business_units TO {readers};
GRANT SELECT ON self_service.guided_tours TO {readers};
