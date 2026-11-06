-- A run's outcome is not kept here. The Jobs API (and later the system.lakeflow tables) is its
-- source of truth; a copy written when the app happened to see the run end could be missing or
-- stale, and could never be more right than the source. This database keeps only what the app
-- owns: the request, its review, comments, decisions, and the link to its run (run_started).
-- A job that could not start has no run to read, so that is the app's to record: start_failed.

DELETE FROM self_service.request_events WHERE type = 'run_finished';
DROP INDEX IF EXISTS self_service.one_finish_per_request;
ALTER TABLE self_service.request_events DROP CONSTRAINT request_events_type_check;
ALTER TABLE self_service.request_events ADD CONSTRAINT request_events_type_check
    CHECK (type IN ('submitted', 'reviewed', 'needs_info', 'replied', 'commented',
                    'approved', 'rejected', 'run_started', 'start_failed', 'withdrawn'));
