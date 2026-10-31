# dev/: the framework repository only

This folder exists only in the framework repository; a release leaves it out (`scripts/release.py`).

| Path | Purpose |
| --- | --- |
| `dev/README.md` | Marks the framework repository: tests that only make sense here (for example `scripts/tests/test_baseline_copy.py`) run when it exists |
| `dev/workspaces/<name>.yaml` | Optional workspaces that test the framework itself, planned and applied like `config/workspaces/` ones, never released |
