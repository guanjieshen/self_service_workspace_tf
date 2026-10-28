# Runbook: setting up the workspace baseline

## Overview

This runbook takes the repository from a zip file to its first governed workspace. It is ordered by **who does what**: each section is one team's checklist, with the values it needs and the command it runs. Most steps happen once; onboarding each further workspace is section 8 only.

| # | Section | Who | When |
| - | --- | --- | --- |
| 0 | [Collect the values](#0-collect-the-values) | Platform team | Once |
| 1 | [Put the repository in your GitHub](#1-put-the-repository-in-your-github) | Platform team | Once |
| 2 | [Decide the baseline](#2-decide-the-baseline) | Platform team, security | Once, before the first apply |
| 3 | [Terraform state storage](#3-terraform-state-storage) | Cloud team | Once |
| 4 | [The pipeline identity](#4-the-pipeline-identity) | Entra admin | Once |
| 5 | [Repository settings](#5-repository-settings) | GitHub organization admin | Once |
| 6 | [Databricks account](#6-databricks-account) | Databricks account admin | Once, then per workspace |
| 7 | [Groups](#7-groups) | Identity team | Per business unit |
| 8 | [Onboard a workspace](#8-onboard-a-workspace) | Platform team | Per workspace |
| 9 | [Day to day](#9-day-to-day) | Platform team | Ongoing |
| 10 | [Troubleshooting](#10-troubleshooting) | Anyone | When needed |

Sections 3 to 7 can run in parallel once section 1 is done, except that section 4 needs the storage account from section 3, and sections 5 and 6 need the client ID from section 4.

Every setup command prints the script it would run, so you can read it first or send it to the team that owns the step; add `--run` to run it. Each one checks before it creates, so running it again is safe.

> [!TIP]
> Run every command from the repository root. Tools: Terraform 1.9+, Python 3.9+, the Databricks CLI, the Azure CLI (`az`) and the GitHub CLI (`gh`), each signed in as the person running that section.

## 0. Collect the values

Fill in this worksheet before you start. None of these values are secrets.

| Value | Example | Provided by | Used in |
| --- | --- | --- | --- |
| Azure tenant ID | `00000000-...` | Entra admin | 5 |
| Azure subscription for the state storage | `00000000-...` | Cloud team | 3, 4, 5 |
| Resource group and region for the state | `rg-databricks-tfstate`, `canadacentral` | Cloud team | 3, 4 |
| Storage account name (3 to 24 lowercase letters and digits, globally unique) | `stdbxcitizendevstate` | Cloud team | 3, 4 |
| GitHub repository | `my-org/databricks-citizen-dev` | GitHub admin | 1, 4, 5 |
| Team that approves applies (optional) | `my-org/databricks-platform` | Platform team | 5 |
| Service principal name | `sp-citizen-dev-terraform` (the default) | Entra admin | 4, 6 |
| Databricks account ID | `00000000-...` (account console, top right) | Databricks account admin | 6, 8 |
| Network path to the workspaces | Public, IP access list or Private Link | Cloud team | 5 (runner) |
| For each workspace: name, business unit code, LOB, URL | `fin-citizen-dev`, `fin`, `FIN`, `https://adb-....azuredatabricks.net` | Platform team | 8 |
| For each business unit: the five Entra groups | `fin_users`, `fin_explorer`, `fin_builder`, `fin_publisher`, `fin_platform_admins` | Identity team | 7 |

## 1. Put the repository in your GitHub

1. Create an **empty private repository** in your GitHub organization (no README, no license).
2. Unzip the release and push it:

   ```bash
   unzip <release>.zip && cd <release>
   git init -b main && git add -A && git commit -m "Workspace baseline v1.0.0"
   git remote add origin https://github.com/<org>/<repo>.git && git push -u origin main
   ```

3. Replace the owners in `.github/CODEOWNERS` with your teams (for example `@my-org/databricks-platform` and `@my-org/security`), in a pull request once section 5 is done. Until then, push directly; afterwards branch protection requires pull requests.

> [!NOTE]
> The repository's GitHub OIDC subject includes its numeric IDs, so create the repository with its final name before section 4. Renaming it later means recreating the two federated credentials (run section 4 again).

## 2. Decide the baseline

The baseline in `config/defaults/` is what every workspace gets. Most of it is a sensible default; these settings need a decision before the first apply, because they are hard to undo or depend on your organization. Change them in a pull request (or before the first push).

| Decision | File and key | Shipped value | Notes |
| --- | --- | --- | --- |
| **Disable legacy access** (Hive metastore, DBFS root and mounts, No-isolation clusters) | `settings.yaml` `disable_legacy_access`, `disable_dbfs_root_and_mounts` | `true` | **One-way after 30 days.** Fine for new workspaces. For an existing one, `preflight.py` lists what still uses legacy access; set both to `null` in that workspace's `settings.yaml` until it is migrated |
| Git URLs allowed in Git folders | `settings.yaml` `git.allowed_urls` | `https://github.com/<org>/` | **Replace the placeholder**; preflight warns until you do |
| Compliance security profile | `settings.yaml` `compliance_security_profile` | `null` (leave alone) | **One-way**, and billed. Only if your compliance team requires it |
| Unity Gateway enforced | `settings.yaml` `enforce_unity_gateway` | `true` | Switches off the `databricks-` pay-per-token endpoints; model calls must use `system.ai` models |
| Collaboration platforms | `settings.yaml` `collaboration_platforms.allowed` | `ALLOW_TEAMS` | `ALLOW_ALL`, `ALLOW_SLACK`, `ALLOW_TEAMS` or `DENY_ALL` |
| Dashboard embedding domains | `settings.yaml` `dashboard_embedding.approved_domains` | none | For example your SharePoint domain |
| Personal access tokens | `settings.yaml` `personal_access_tokens`, `access.yaml` `personas.<persona>.can_create_tokens` | On, 90 days, no persona may create them | Only admins create tokens unless a persona is allowed |
| Group names | `access.yaml` `groups` | `{bu}_users`, `{bu}_explorer`, ... | Match your Entra naming convention; `{bu}` is the workspace's business unit code |
| Required tags | `cost.yaml` `required_tags` | `LOB`, `DEPARTMENT`, `TEAM` | Changing them later affects new workloads only |
| Budget (usage) policies | `cost.yaml` `budget_policies.enabled` | `true` | Needs an account-level permission for the pipeline (section 6); set `false` if you will not grant it. Data classification needs them |
| Catalog name and features | `catalog.yaml` `catalog` | `{bu}_citizen_dev`, predictive optimization, data classification and data quality monitoring on | `catalog.storage_root` is needed when the metastore has no storage root (preflight says so) |
| Restrict workspace admins | `settings.yaml` `restrict_workspace_admins` | `false` | Needs account admin to change; leave `false` |
| AI review of each plan | `config/ai-review.yaml` | On, `system.ai.claude-sonnet-5-5` | Advice in the plan comment only; set `enabled: false` if models are not available |

What each setting does is in the comment beside it, and in [config/README.md](../config/README.md).

## 3. Terraform state storage

**Who:** the cloud team, with Contributor on the subscription (or the resource group).

```bash
python3 scripts/setup.py state --subscription <subscription-id> \
  --resource-group rg-databricks-tfstate --location canadacentral \
  --storage-account stdbxcitizendevstate
```

Review the printed script, then run it again with `--run`. It creates a storage account with no public blob access and no shared keys (Entra sign-in only), with versioning and 30 days of soft delete, a private `tfstate` container, and `config/backend.hcl`. Commit `config/backend.hcl`: it holds names, not secrets. Run outside the repository, the script prints the file's content instead, to send to the platform team.

## 4. The pipeline identity

**Who:** an Entra admin who can create app registrations and assign roles on the storage account (Owner or User Access Administrator), signed in to `gh` with read access to the repository.

```bash
python3 scripts/setup.py identity --subscription <subscription-id> \
  --resource-group rg-databricks-tfstate --storage-account stdbxcitizendevstate \
  --repo <org>/<repo>
```

It creates the app registration and service principal `sp-citizen-dev-terraform`, two federated credentials for GitHub Actions, and gives the service principal **Storage Blob Data Contributor** on the state container only. It prints the three IDs the next sections need: client ID, tenant ID, subscription ID.

| Federated credential | Subject | Lets sign in |
| --- | --- | --- |
| `github-pull-requests` | `<repo prefix>:pull_request` | The Plan workflow, on every pull request |
| `github-main` | `<repo prefix>:ref:refs/heads/main` | The Apply and Drift workflows, from `main` |

No client secret is created: GitHub exchanges its own short-lived token for an Entra token on each run. One service principal serves every workspace, so new workspaces need nothing here.

## 5. Repository settings

**Who:** a GitHub organization admin (or a repository admin), signed in to `gh`.

```bash
python3 scripts/setup.py github --repo <org>/<repo> \
  --client-id <client-id> --tenant-id <tenant-id> --subscription <subscription-id> \
  --approvers <org>/databricks-platform        # optional: who approves each apply
```

It sets the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`, creates the labels `allow-risky-changes` and `drift`, the environment `apply-approval` (deployments from `main` only; with `--approvers`, that team must approve each apply), and protects `main`: pull requests only, the **Format and validate** and **Tests** checks must pass, and code owners must approve.

Then, if needed:

- **Private networking.** If the workspaces use Private Link or an IP access list, GitHub-hosted runners cannot reach them. Register a self-hosted runner inside the network (or use GitHub's Azure private networking) and set the repository variable `TERRAFORM_RUNNER`, for example `"citizen-dev"` with the quotes ([docs/github-actions.md](github-actions.md)).
- **Write access.** Only the platform team should be able to push branches: a pull request's plan runs with the pipeline's workspace-admin rights before review ([docs/github-actions.md](github-actions.md), "Who can run code with the workspace credentials").

> [!WARNING]
> Required reviewers and branch protection need GitHub Team or Enterprise for private repositories. Without them, merging is the only approval and nothing stops a merge before its plan finishes: wait for every check first.

## 6. Databricks account

**Who:** a Databricks account admin, signed in with the Databricks CLI to the account (`databricks auth login --host https://accounts.azuredatabricks.net --account-id <account-id>`, or an account profile).

1. Add the service principal to the account, and make it workspace admin of each workspace already in `config/workspaces/` (none yet on a fresh install; run it again per workspace in section 8):

   ```bash
   python3 scripts/setup.py databricks --client-id <client-id> [--account-profile <profile>] [<workspace> ...]
   ```

2. In the account console, give the service principal the permission to create **budget policies** (serverless usage policies), or set `budget_policies.enabled: false` in `config/defaults/cost.yaml`.
3. Check that each workspace's metastore can hold the workspace catalog: either the metastore has a storage root, or the workspace's `catalog.yaml` sets `catalog.storage_root` to an external location (the Unity Catalog team creates the storage credential and external location). Preflight checks this.

The service principal is never account admin: it needs workspace admin in the workspaces it manages, plus the budget policy permission.

## 7. Groups

**Who:** the identity team.

For each business unit, create five Entra ID groups and sync them to the Databricks account (automatic identity management or SCIM provisioning): by default `{bu}_users`, `{bu}_explorer`, `{bu}_builder`, `{bu}_publisher`, `{bu}_platform_admins`. They must be **account groups**: Unity Catalog grants and usage policies cannot use groups created inside a workspace. Terraform assigns them to the workspace; it never adds people. Who is in each group stays in Entra ID.

| Group | Gets |
| --- | --- |
| `{bu}_users` | Consumer access (Databricks One): dashboards, Genie spaces, apps |
| `{bu}_explorer` | SQL access: the SQL editor, queries, dashboards, Genie |
| `{bu}_builder`, `{bu}_publisher` | Workspace access: notebooks, jobs, the shared cluster, one personal cluster |
| `{bu}_platform_admins` | Workspace admin; owns the workspace catalog |

## 8. Onboard a workspace

**Who:** the platform team. Repeat for every workspace.

1. **Create its folder:**

   ```bash
   python3 scripts/workspaces.py new fin-citizen-dev --bu fin --lob FIN \
     --host https://adb-1234567890123456.7.azuredatabricks.net --account-id <account-id>
   ```

2. **Make the pipeline workspace admin there** (a Databricks account admin): `python3 scripts/setup.py databricks --client-id <client-id> fin-citizen-dev --run`.
3. **Review the files** in `config/workspaces/fin-citizen-dev/`. Most are comments; set only what this workspace changes from the baseline (for example `catalog.storage_root`, or `settings.disable_legacy_access: null` for an existing workspace that is not ready).
4. **Check it is ready** (read-only), signed in as yourself with the Azure or Databricks CLI:

   ```bash
   python3 scripts/preflight.py fin-citizen-dev
   ```

   It checks the sign-in and admin rights, the metastore, that every group is an account group, the catalog's storage, what still uses legacy access, and placeholders left in the baseline. Fix every `error` before the pull request; read every `warning`.
5. **Open a pull request** with the folder. The Plan workflow runs preflight again as the pipeline, then plans, and posts the plan, the plan guard's warnings and the AI review as a comment. The first plan creates everything; check that it changes nothing you did not expect.
6. **Merge.** The Apply workflow waits for approval in `apply-approval` (if it has reviewers), then applies.
7. **Verify:** the next pull request (or the Monday drift check) shows no changes for the workspace. In the workspace: the persona groups under Settings > Identity and access, the `<BU> Default Warehouse`, the `{bu}_citizen_dev` catalog, and the `<BU> personal schema` and `<BU> team folder` jobs.

> [!WARNING]
> Applying the baseline to an existing workspace changes its settings for everyone in it (downloads, tokens, Git folders, legacy access). Read the plan comment's settings changes with the workspace's owners before merging.

## 9. Day to day

| Task | How |
| --- | --- |
| Give someone a persona | Add them to the group in Entra ID; no change here |
| Change one workspace | Pull request editing `config/workspaces/<name>/`: only that workspace is planned and applied |
| Change every workspace | Pull request editing `config/defaults/`: every workspace is planned, and applied one at a time, stopping at the first failure |
| Create a personal schema or a team folder | Run the `<BU> personal schema` or `<BU> team folder` job (admins), or let a service principal run them (`jobs.runners` in `access.yaml`, for example a ticketing system) |
| A plan is flagged as risky | Review the warning in the plan comment; if intended, a person adds the label `allow-risky-changes` |
| A `drift` issue opens | Someone changed a setting by hand: update the configuration to match, or re-apply to restore it |
| Retry a failed apply | Fix the cause, then re-run the latest Apply run (it refuses if `main` has moved on) |
| Upgrade to a new release | [README.md](../README.md), "Installing and upgrading": the pull request's plan shows what the new version changes in each workspace |

More: [config/README.md](../config/README.md) (configuration tasks) and [docs/github-actions.md](github-actions.md) (the workflows).

## 10. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No matching federated identity record found for presented assertion` (an `AADSTS` error at sign-in) | The token's subject is not one of the two credentials: the repository was renamed or transferred, or a workflow ran from a branch other than `main` (Drift or Apply run by hand on a branch) | Run section 4 again (it reads the current subject prefix); run Apply and Drift only from `main` |
| `Source IP address ... is blocked by Databricks IP ACL`, or a timeout reaching the workspace | GitHub-hosted runners cannot reach the workspace | A runner inside the network and `TERRAFORM_RUNNER` (section 5) |
| `AuthorizationPermissionMismatch` or `403` reading the state | The role on the state container is missing or still propagating | Wait a few minutes after section 4; check Storage Blob Data Contributor on the container |
| `state blob is already locked` | Two runs on the same workspace at once (a pull request plan and an apply) | Wait for the other run, then re-run |
| Preflight: `is not a workspace admin` | Section 6 not done for this workspace | `setup.py databricks --client-id <id> <workspace> --run` |
| Preflight: group `does not exist in the account` or `exists only in this workspace` | The Entra group is missing, not synced, or a workspace-local group has the same name | Section 7; or name the right group under `groups:` in the workspace's `access.yaml` |
| Preflight: `the metastore has no storage root` | New catalogs have nowhere to store data | Set `catalog.storage_root` in the workspace's `catalog.yaml` to an external location URL |
| Apply fails creating a budget policy (permission denied) | The service principal lacks the account-level budget policy permission | Section 6, step 2, or `budget_policies.enabled: false` |
| `Usage policy ID must not be empty` | Data classification runs on serverless and needs a usage policy | Turn on budget policies, or set `catalog.data_classification: null` |
| A local plan shows permission changes that CI does not | Local plans run as you, not the pipeline: the owner entry differs | Trust the CI plan and the drift check |
| The plan comment has no AI review | The model is unavailable to the pipeline in that workspace (region, Unity Gateway, missing EXECUTE) | Set a model in the workspace's `ai-review.yaml`, or `enabled: false`; the review is advice only |
| Apply ran straight after the merge, without approval | `apply-approval` has no required reviewers (or the GitHub plan does not support them) | Add reviewers to the environment (section 5, `--approvers`) |
