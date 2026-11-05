-- Settings people change from the approvals app (its Settings page): links and the banner.
-- Their defaults stay in app.yaml; a row here overrides one, and a row with a null value goes
-- back to it. Append-only like request_events, so every change says who made it and when.

CREATE TABLE self_service.setting_events (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key   text NOT NULL,                          -- settings.py SETTINGS, for example faq.data
    value text,                                   -- null = back to app.yaml's value
    actor text NOT NULL,                          -- who changed it (an email)
    at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX setting_events_by_key ON self_service.setting_events (key, id DESC);

-- Each setting's latest change.
CREATE VIEW self_service.settings AS
SELECT DISTINCT ON (key) key, value, actor, at FROM self_service.setting_events ORDER BY key, id DESC;
