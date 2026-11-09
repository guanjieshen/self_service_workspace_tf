-- Who has had the guided tour: the Open your workspace card opens Genie One with the onboarding
-- prompt the first time, and plain Genie One after that. Append-only like the other tables: each
-- tour is a row (Start the guided tour again adds one), so the history says how often.

CREATE TABLE self_service.guided_tours (
    id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,                          -- who (lower case)
    at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX guided_tours_by_email ON self_service.guided_tours (email);
