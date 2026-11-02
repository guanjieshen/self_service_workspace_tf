-- A run ends once: the app records it the first time it sees the run end (on the status page
-- or My Requests), so seeing it again must change nothing.
CREATE UNIQUE INDEX one_finish_per_request ON self_service.request_events (request_id)
    WHERE type = 'run_finished';
