# Changelog

Releases are git tags (`v1.0.0`). Each entry says what the first plan after an upgrade
shows, and lists new baseline settings to add to `config/defaults/` (an upgrade never adds
them for you: a setting missing from your baseline is left alone).

## Unreleased

- CI signs in with one service principal and two federated credentials (pull requests;
  `main`) instead of two GitHub Environments and one credential per workspace. Onboarding a
  workspace needs nothing in GitHub or Entra. One `apply-approval` environment gates applies.
- `scripts/setup.py`: the one-time setup as one command per team (state storage, the
  identity, repository settings, the Databricks account), printed first, `--run` to run.
- `scripts/preflight.py`: read-only checks that a workspace is ready (sign-in, admin rights,
  account groups, catalog storage, legacy access, baseline placeholders). The Plan workflow
  runs it and shows problems in the plan comment.
- `docs/SETUP.md`: setting up an organization's instance, by team, starting from one flat file of
  values, `config/setup.yaml`: four required at the top, optional ones with defaults below, and
  the two IDs `setup.py identity` writes. Every `setup.py` step reads it (no flags to retype).

## 1.0.0

First release of the workspace baseline on its own: settings, personas, compute, the
workspace catalog, usage policies, Genie Code, and the on-request personal schema and team
folder jobs, with the plan, apply and drift workflows.
