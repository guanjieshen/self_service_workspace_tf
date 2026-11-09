-- The business unit each person chose in the self-service app, while there is no lookup function
-- (bu_lookup) to say it for them. Append-only like the other tables: a new choice is a new row,
-- and the latest one counts, so the history says when someone moved.

CREATE TABLE self_service.business_unit_choices (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,                          -- who chose (lower case)
    bu    text NOT NULL,                          -- a served workspace's prefix, upper case
    at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX business_unit_choices_by_email ON self_service.business_unit_choices (email, id DESC);

-- Each person's latest choice.
CREATE VIEW self_service.chosen_business_units AS
SELECT DISTINCT ON (email) email, bu, at FROM self_service.business_unit_choices ORDER BY email, id DESC;
