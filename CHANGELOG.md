# Changelog

Releases are git tags (`v1.0.0`). Each entry says what the first plan after an upgrade
shows, and lists new baseline settings to add to `config/defaults/` (an upgrade never adds
them for you: a setting missing from your baseline is left alone).

## Unreleased

- **A workspace is one file**, `config/workspaces/<name>.yaml`: `bu`, `host`, `groups`, and any
  baseline key it changes, at the top level. The files are the list of workspaces. Replaces the
  workspace folders (`workspace.yaml`, `access.yaml`, ...). Add one by copying `_example.yaml`.
- **One deploy workflow** (`deploy.yml`): it works out which workspaces a change concerns and
  runs one job per workspace (plan on pull requests, apply on merge, drift on Mondays). A
  deleted workspace file removes that workspace's state. Replaces the per-workspace workflows.
  A plan with no changes gets no comment. `CHECKS_RUNNER` picks the runner for the checks.
- `account_id` is set once, in `config/defaults/cost.yaml` (required while budget policies are on).
- `tags:` in a workspace file replaces `lob` and the automatic `LOB` tag: any tags with one value
  for the whole workspace. Genie Code text uses `{TAGS}` and `{WORKSPACE_TAGS}` instead of `{LOB}`.
- Genie Code skills come from the baseline only; a workspace adds instructions as text
  (`genie_code_instructions`). The skill format is checked by `scripts/tests/test_genie_skills.py`.
- `workspaces.py new` is gone (copy `_example.yaml`); `docs/user-journeys.md` walks through the
  everyday changes.

- The AI plan review uses one review workspace's model for every plan
  (`ai_review_workspace` and `ai_review_model` in `config/setup.yaml`; off until set).
  Removed `config/ai-review.yaml` and the per-workspace `ai-review.yaml` files.
- Removed `config/backend.hcl.example`: `setup.py state` writes `config/backend.hcl`.

- Self-service is the app's: removed the team folder and personal schema jobs, their
  notebooks and the admin folder, `jobs.runners`, `personal_schemas`, shared schemas
  (`catalog.schemas`) and data quality monitoring (it watched those schemas).
- Removed the `manage` switches: group assignment, token permissions and catalog grants
  are always managed.
- Persona groups are named per workspace (`groups:` in its `access.yaml`); the baseline
  names only `{bu}_platform_admins`. A persona without a group is skipped.

- CI signs in with one service principal and two federated credentials (pull requests;
  `main`) instead of two GitHub Environments and one credential per workspace. Onboarding a
  workspace needs nothing in GitHub or Entra. One `apply-approval` environment gates applies.
- `scripts/setup.py`: the one-time setup as one command per team (state storage, the
  identity, repository settings), printed first, `--run` to run. The Databricks account step
  (service principal, workspace admin, budget policy permission) is a checklist done by hand.
- `scripts/preflight.py`: read-only checks that a workspace is ready (sign-in, admin rights,
  account groups, catalog storage, legacy access, baseline placeholders). The Plan workflow
  runs it and shows problems in the plan comment.
- `docs/SETUP.md`: setting up an organization's instance, by team, starting from one flat file of
  values, `config/setup.yaml`: the values your organization decides at the top (required, never
  guessed), optional ones with defaults below (`github_repo` defaults to the clone's GitHub
  origin, and steps 4 and 5 print which repository they use), and the client ID `setup.py identity` writes.
  The Azure steps stop unless the Azure CLI is signed in to `tenant_id`. Every `setup.py` step reads it (no flags to retype).

## 1.0.0

First release of the workspace baseline on its own: settings, personas, compute, the
workspace catalog, usage policies, Genie Code, and the on-request personal schema and team
folder jobs, with the plan, apply and drift workflows.
