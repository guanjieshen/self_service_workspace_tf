# Changelog

Releases are git tags (`v1.0.0`). Each entry says what the first plan after an upgrade
shows, and lists new baseline settings to add to `config/defaults/` (an upgrade never adds
them for you: a setting missing from your baseline is left alone).

## Unreleased

- Preflight checks that the pipeline may create usage policies (the account's **Billing admin**
  role; an error, before the plan) and warns when the platform admins group is empty. A plan with
  `catalog.data_classification: true` fails with why (the provider cannot send its usage policy yet).
- Data classification is left alone by default (`catalog.data_classification: null`): the API
  now requires a `usage_policy_id` the Terraform provider cannot send yet (up to 1.140.0), so
  turning it on failed every apply. Turn it on in Catalog Explorer, with the workspace's usage policy.
- The identity running Terraform (the pipeline's service principal) may use the workspace's
  serverless usage policy, and data classification waits for it: turning classification on
  failed with "Usage policy ID must not be empty". The service principal needs the account's
  **Billing admin** role to create the policy (`docs/SETUP.md`, step 6).
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
