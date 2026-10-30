# Changelog

Releases are git tags (`v1.0.0`). Each entry says what the first plan after an upgrade
shows, and lists new baseline settings to add to `config/defaults/` (an upgrade never adds
them for you: a setting missing from your baseline is left alone).

## Unreleased

- The chargeback tag `APP_ID` is now `APPID` (the baseline's `tags:`, `classic_user_tags`, and
  `tags:` in workspace files). The first plan updates the tags on the usage policy, the warehouse
  and the classic cluster policies; cost reports show `APP_ID` before and `APPID` after.
- **`bu` is now `prefix`** in workspace files, and the placeholders `{bu}` / `{BU}` are `{prefix}` /
  `{PREFIX}`: it is the short code that starts every name Terraform creates in a workspace. Rename
  the key in each workspace file (and the placeholders in `config/defaults/`); the plan shows no
  changes. A file that still says `bu:` fails the plan with its name.
- The plan comment reads like a review: the AI writes a risk summary, what it means, what changes
  (a before/after table) and what to review, adapted to the risk; **Before merging** comes from
  the plan guard alone (only when it flagged something); the guard's findings, the changed
  resources and the plan move to a collapsed **Technical details**. The guard prints a plain
  header instead of an ASCII banner. Enforcement is unchanged.
- The AI review also reads the Terraform code and CHANGELOG diff (`<code_diff>`), so a
  framework change is explained instead of reported as unexplained drift, and is calibrated
  against false alarms: a security change made on purpose with a reason is Medium, the
  pipeline's own grant removed by the code is Low, and nothing is High only because it is
  unknown. Two evaluation cases from real pull requests; 20/20 with Opus (17/20 before).
- The Git allowlist allows every github.com repository (`https://github.com/`) instead of the
  placeholder `https://github.com/<org>/`, which matched none; other Git hosts stay blocked. Add a
  GitHub Enterprise host to `allowed_urls` when you have one.
- Data classification and data quality monitoring are turned on by hand in Catalog Explorer
  (`docs/SETUP.md`, step 9): removed `catalog.data_classification` and its checks. The
  classification API needs a usage policy ID the Terraform provider cannot send, and
  monitoring is per schema, and schemas come from the self-service app.
- CI hardening, no change in what it deploys: permissions per job, actions pinned to commit
  SHAs (with Dependabot), no token kept in checkouts, time limits on every job. Less noise:
  plans do not take the state lock (no more collisions with applies), a newer push cancels
  older plans, fork pull requests are not planned, an unchanged drift is not re-reported, and
  preflight warnings alone no longer post a comment on a plan without changes.
- Preflight checks that the pipeline may create usage policies (the account's **Billing admin**
  role; an error, before the plan) and warns when the platform admins group is empty.
- The Serverless Starter Warehouse Databricks creates in a new workspace is for the platform
  admins only (`starter_warehouse.admins_only` in `config/defaults/compute.yaml`): people use
  the default warehouse, which is sized and tagged. Only its permissions are managed. The first
  plan creates `module.compute.databricks_permissions.starter_warehouse`; anyone using it loses
  access, so check an existing workspace first, or set it to `null` there.
- A new workspace's first apply no longer needs `allow-risky-changes` for disabling legacy
  access: the plan guard reads preflight's findings and lets it through when nothing still
  uses legacy access. An existing workspace that still uses Hive or DBFS mounts is flagged as before.
- **Compute and chargeback: serverless first, Terraform holds only what rarely changes.**
  What a team or project requests (warehouses, usage policies, classic compute access) is
  the self-service app's.
  - **One tag list:** `tags:` and `classic_user_tags` in `config/defaults/cost.yaml`, on
    the usage policy, the default warehouse and every classic cluster. `tags:` is now a
    baseline key: a workspace file changes a value (its `APP_ID`), adds a tag, or drops one
    with `null`. Replaces `required_tags`, the warehouses' and cluster's own `tags`, and the
    automatic `PERSONA` tag.
  - **One serverless usage policy** per workspace, `{BU}-0-SELF-SERVICE`, for every
    persona and the platform admins (`serverless_policy` replaces `budget_policies`: no
    `policies` blocks, `used_by` or `extra_managers`).
  - **Three classic cluster policies**, one per kind of cluster: `{BU} Classic Interactive`,
    `{BU} Classic Jobs` and `{BU} Classic Pipelines`, one cluster per person each, from one
    set of rules (`cluster_policy`). The tags are fixed, except `classic_user_tags`, which
    users must fill in (upper case, digits, `_`, `-`). Terraform does not manage who may use
    them; the app grants them. A kind set to `null` is left alone (released), never deleted.
  - **Removed:** the per-persona cluster policies (and the persona keys `cluster_policy` and
    `shared_cluster`), the shared cluster, the classic warehouse, `teams` and
    `team_warehouses`. A workspace file that still has one of these keys fails the plan
    with the key's name.
  - **The first plan** on an applied workspace deletes the persona cluster policies, the
    shared cluster, the classic and team warehouses, and the `{BU}-SHARED` and
    `{BU}-PLATFORM` usage policies; creates `{BU}-0-SELF-SERVICE` and the three classic
    policies; and updates the tags on the default warehouse. The plan guard flags the
    deletes. Before merging, check what still uses them: jobs pinned to the old usage
    policies or the shared cluster, clusters created from the persona policies.
- The AI review judges risk by what could break, who could lose access and whether it can be
  undone, using preflight's findings as evidence (a plan guard warning means a person must
  approve; it is not High on its own). Releases (`null`) are described as "Terraform stops
  managing it". Evaluation cases in `.github/ai/eval/` and `scripts/ai-review-eval.py` check the
  review on eight realistic pull requests.

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
  (`ai_review_host`, any workspace the pipeline can sign in to, and `ai_review_model` in
  `config/setup.yaml`; off until set).
  Removed `config/ai-review.yaml` and the per-workspace `ai-review.yaml` files.
- Removed `config/backend.hcl.example`: `setup.py state` writes `config/backend.hcl`.

- Self-service is the app's: removed the team folder and personal schema jobs, their
  notebooks and the admin folder, `jobs.runners`, `personal_schemas`, shared schemas
  (`catalog.schemas`) and data quality monitoring (it watched those schemas).
- Removed the `manage` switches: group assignment, token permissions and catalog grants
  are always managed.
- Persona groups are named per workspace (`groups:` in its file); the baseline
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
