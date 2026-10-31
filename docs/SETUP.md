# Setup: from the zip to the first workspace

## Overview

This guide takes the repository from a zip file to its first governed workspace. It is ordered by **who does what**: each step is one team's checklist, with the values it needs and the command it runs. Most steps happen once. Onboarding each further workspace repeats step 6 (items 2 and 5), step 7 and step 9.

| # | Step | Who | When |
| - | --- | --- | --- |
| 1 | [Fill in `config/setup.yaml`](#1-fill-in-configsetupyaml) | Platform team, with the values from each team | Once |
| 2 | [Put the repository in your GitHub](#2-put-the-repository-in-your-github) | Platform team | Once |
| 3 | [Terraform state storage](#3-terraform-state-storage) | Cloud team | Once |
| 4 | [The pipeline identity](#4-the-pipeline-identity) | Entra admin | Once |
| 5 | [Repository settings](#5-repository-settings) | GitHub organization admin | Once |
| 6 | [Databricks account (by hand)](#6-databricks-account-by-hand) | Databricks account admin | Once, then per workspace |
| 7 | [Groups](#7-groups) | Identity team | Per workspace |
| 8 | [Decide the baseline](#8-decide-the-baseline) | Platform team, security | Once, before the first apply |
| 9 | [Onboard a workspace](#9-onboard-a-workspace) | Platform team | Per workspace |
| 10 | [Day to day](#10-day-to-day) | Platform team | Ongoing |
| 11 | [Troubleshooting](#11-troubleshooting) | Anyone | When needed |

Steps 3 to 8 can run in parallel once step 2 is done, except that step 4 needs the storage account from step 3, and steps 5 and 6 need the client ID from step 4. **Push what steps 3 and 4 write (`config/backend.hcl`, the client ID in `config/setup.yaml`) to `main` before step 5:** step 5 protects `main`, and after it every change goes through a pull request with an approval.

Steps 3 to 5 are commands that read their values from `config/setup.yaml`; step 6 is done by hand in the Databricks account console. Each command prints the script it would run, so you can read it first or send it to the team that owns the step; add `--run` to run it. Each one checks before it creates, so running it again is safe.

> **Tip:** Run every command from the repository root. Tools: git, Terraform 1.9+, Python 3.9+, the Databricks CLI, the Azure CLI (`az`) and the GitHub CLI (`gh`), each signed in as the person running that step. Node.js 22 runs the plan comment's tests.

## 1. Fill in `config/setup.yaml`

**This is the first file you edit.** Every **required** value is a fact about your environment or a decision your organization makes, so nothing guesses it; the **optional** values have defaults that suit most organizations; the last value is written by step 4. None of them are secrets: the file is committed with the repository. A step that needs a value that is still empty stops and names it.

```yaml
# ---- REQUIRED ----
tenant_id: 00000000-0000-0000-0000-000000000000
subscription_id: 00000000-0000-0000-0000-000000000000
state_location: canadacentral
state_resource_group: rg-databricks-tfstate
state_storage_account: stdbxcitizendevstate
state_container: tfstate

# ---- OPTIONAL ----
github_repo: null
pipeline_name: null
apply_approvers: my-org/databricks-platform
ai_review_host: null
ai_review_model: null

# ---- WRITTEN BY SETUP ----
pipeline_client_id: null
```

| Value | What it is | Who provides it | Used in step |
| --- | --- | --- | --- |
| **`tenant_id`** | Your Entra tenant. CI signs in to it, and the Azure steps stop unless your Azure CLI is signed in to it | Entra admin | 3, 4, 5 |
| **`subscription_id`** | The Azure subscription that holds the Terraform state | Cloud team | 3, 4, 5 |
| **`state_location`** | The region of the state storage (a data residency decision) | Cloud team | 3 |
| **`state_resource_group`** | The resource group for the state storage (created if missing) | Cloud team | 3, 4 |
| **`state_storage_account`** | 3 to 24 lowercase letters and digits, unique across Azure (created if missing; an existing one is used as it is) | Cloud team | 3, 4 |
| **`state_container`** | The blob container for the state files, for example `tfstate` | Cloud team | 3, 4 |
| `github_repo` | The repository that runs the pipeline, `<org>/<repo>`: Entra lets only its pull requests and `main` branch sign in, and step 5 configures it. Default: this clone's GitHub origin (steps 4 and 5 print which one they use). Set it only to run setup from a copy without that origin | GitHub admin | 4, 5 |
| `pipeline_name` | Display name of the service principal CI signs in as. Default `sp-citizen-dev-terraform` | Entra admin | 4, 6 |
| `apply_approvers` | `<org>/<team>` that must approve each apply in GitHub. Default: none, merging approves | Platform team | 5 |
| `ai_review_host`, `ai_review_model` | The URL (`https://adb-<id>.<n>.azuredatabricks.net`, not a custom URL) of the workspace whose model reviews every plan, and the model. Any workspace the pipeline's service principal can sign in to; it need not be one this repository manages. Default: no AI review; the model `system.ai.claude-sonnet-5-5` | Platform team | any time |
| `pipeline_client_id` | The service principal's client ID: step 4 creates it and writes it here | | 5, 6 (by hand) |

Two more things to know before you start; they live in their own files, not here:

| What | Example | Who | Where it goes |
| --- | --- | --- | --- |
| The network path to the workspaces | Public, IP access list or Private Link | Cloud team | Step 5: a runner, if not public |
| For each workspace: name, prefix (starts every name Terraform creates there), URL | `fin-citizen-dev`, `fin`, `https://adb-....azuredatabricks.net` | Platform team | Step 9: its file |
| The Databricks account ID | `00000000-...` | Databricks account admin | Step 8: `account_id` in `config/defaults/cost.yaml` |
| For each workspace: its persona groups; for each workspace prefix: `{prefix}_platform_admins` | `fin_platform_admins`, `fin-cd-explorers`, ... | Identity team | Step 7; persona groups in each workspace's file |

## 2. Put the repository in your GitHub

> **On GitHub Enterprise?** Read [github-enterprise.md](github-enterprise.md) first: it covers the issuer and subject differences, self-hosted runners, and what to check.

1. Create an **empty private repository** in your GitHub organization (no README, no license).
2. Unzip the release and push it:

   ```bash
   unzip <release>.zip && cd <release>
   # config/setup.yaml filled in (step 1)
   git init -b main && git add -A && git commit -m "Workspace baseline v1.0.0"
   git remote add origin https://github.com/<org>/<repo>.git && git push -u origin main
   ```

3. **Push only what you want deployed.** Once step 5 is done, every push to `main` applies the workspaces that push concerns: the `config/workspaces/` files it changes, or every workspace when it changes `config/defaults/` or the Terraform code ([github-actions.md](github-actions.md)). A release ships with none (only `_example.yaml`), so the first push deploys nothing.
4. **Replace the owners in `.github/CODEOWNERS`** with your teams (for example `@my-org/databricks-platform` and `@my-org/security`) **before step 5**, in this push or a direct one after it. Step 5 turns on branch protection that requires code owners to review, so a placeholder owner would leave nobody able to approve.

> **Note:** The repository's GitHub OIDC subject includes its numeric IDs, so create the repository with its final name before step 4. Renaming it later means recreating the two federated credentials (update `github_repo` and run step 4 again).

## 3. Terraform state storage

**Who:** the cloud team, with Contributor on the subscription (or the resource group).

Terraform keeps one state file per workspace in an Azure Storage container. CI reads and writes it with its Entra identity (step 4), so no storage key is ever used.

> **Storage account and container already exist?** Skip the script and [do it by hand](#using-an-existing-storage-account-and-container): it is one small file.

To create them, use the setup script. It uses `tenant_id`, `subscription_id` and the `state_*` values from `config/setup.yaml`:

```bash
python3 scripts/setup.py state          # prints the script: read it
python3 scripts/setup.py state --run    # runs it
```

It creates a storage account with no public blob access and no shared keys (Entra sign-in only), with versioning and 30 days of soft delete, a private container, and `config/backend.hcl`. An account that already exists is left as it is. Commit `config/backend.hcl`: it holds names, not secrets. Run outside the repository, the script prints the file's content instead, to send to the platform team.

### Using an existing storage account and container

Create `config/backend.hcl` (or overwrite the one in the repository) with your names, and commit it:

```hcl
# Shared Terraform state in Azure Storage (Entra sign-in only).
# scripts/tf.sh adds key=citizen-dev/<workspace>.tfstate for each workspace.
resource_group_name  = "<resource group>"
storage_account_name = "<storage account>"
container_name       = "<container>"
use_azuread_auth     = true
```

Then check the account against this list:

| Setting | Required? | Why |
| --- | --- | --- |
| **Container is private** (no anonymous access) | Required | State files hold resource IDs and settings |
| **The runners can reach it** (its network rules or private endpoint) | Required | Plans and applies read and write the state |
| **Storage Blob Data Contributor** for the pipeline identity, on the container | Required, in [step 4](#4-the-pipeline-identity) | CI signs in with Entra, not with keys |
| **Versioning and soft delete** on blobs | Recommended | Lets you recover a state file that was overwritten or deleted |
| **Shared key access off** | Recommended | Nothing in this project uses keys |

Fill in `state_resource_group`, `state_storage_account` and `state_container` in `config/setup.yaml` too: step 4 uses them to scope the storage role.

## 4. The pipeline identity

**Who:** an Entra admin who can create app registrations and assign roles on the storage account (Owner or User Access Administrator), signed in to `gh` with read access to the repository.

GitHub Actions signs in as one Entra service principal, for every workspace and for the Terraform state. **No client secret is stored anywhere.** On each run, GitHub issues a short-lived OIDC token, Entra checks it against a *federated credential* on the app registration, and hands back an access token for the service principal. That token is then used for the state storage (step 3) and for Databricks (step 6).

The quickest way is the setup script. It uses `tenant_id`, `subscription_id`, the `state_*` values, `github_repo` and `pipeline_name`:

```bash
python3 scripts/setup.py identity          # shows the commands it would run
python3 scripts/setup.py identity --run    # runs them
```

It writes the client ID (`pipeline_client_id`) into `config/setup.yaml` for the next steps. Commit the file.

### What the app registration needs

Whether you run the script or set it up by hand, this is everything on the Entra side:

| Item | Value | Why |
| --- | --- | --- |
| **App registration** and its service principal | Any name, for example `pipeline_name` (`sp-citizen-dev-terraform`) | The identity CI signs in as |
| **Federated credential** `github-pull-requests` | Subject `<prefix>:pull_request` | Lets plans sign in, on every pull request |
| **Federated credential** `github-main` | Subject `<prefix>:ref:refs/heads/main` | Lets applies, drift checks and retirements sign in, from `main` |
| **Role** on the state container | **Storage Blob Data Contributor**, scoped to the container only | Reads and writes the Terraform state |

Both federated credentials use the issuer `https://token.actions.githubusercontent.com` and the audience `api://AzureADTokenExchange` (the defaults).

`<prefix>` is your repository's subject prefix. Read it with:

```bash
gh api repos/<org>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix
```

For example `repo:my-org@123456/my-repo@456789`. Repositories created or renamed since July 15, 2026 include numeric IDs.

**Not needed:** client secrets or certificates, API permissions (Microsoft Graph or others), redirect URIs, or one credential per workspace. Adding a workspace later needs nothing in Entra.

> **Do not use the "Environment" entity type.** A job that runs in a GitHub Environment signs in with the subject `environment:<name>`, which matches neither credential, so the sign-in fails. This repository's jobs that sign in never use an environment; `apply-approval` is only an approval step.

### Setting it up in the Azure portal

If your team does not run the script, do this by hand:

1. **Create the app registration:** Microsoft Entra ID > App registrations > New registration. Leave the redirect URI empty.
2. **Add the first federated credential:** the app > Certificates & secrets > Federated credentials > Add credential > **GitHub Actions deploying Azure resources**.
   - Organization and Repository: your repository.
   - Entity type: **Pull request**.
   - Name: `github-pull-requests`.
3. **Add the second:** the same, with Entity type **Branch** and branch `main`. Name: `github-main`.
4. **Check both subjects** match `<prefix>:pull_request` and `<prefix>:ref:refs/heads/main`. If your repository's prefix includes numeric IDs, use **Edit (optional)** under the subject to enter it exactly.
5. **Grant the role:** the storage account > Containers > the state container > Access control (IAM) > Add role assignment > **Storage Blob Data Contributor** > the app's service principal.
6. **Copy the Application (client) ID** into `pipeline_client_id` in `config/setup.yaml`.

### Checking it

```bash
az ad app federated-credential list --id <application-id> --query "[].{name:name, subject:subject}" -o table
```

You should see exactly the two credentials above, with your repository's prefix. Credentials for other repositories can stay; they do not affect this one.

| If a run fails with | It means |
| --- | --- |
| `AADSTS70021: No matching federated identity record found` | A subject does not match: check the prefix, and that the job is not in an environment |
| `AuthorizationPermissionMismatch`, or `403` reading the state | The storage role is missing, or still propagating (wait a few minutes) |
| `the repository variables ... are not set` | Step 5 is not done yet |

The Databricks side of the same identity (account, workspace admin, Billing admin) is [step 6](#6-databricks-account-by-hand).

## 5. Repository settings

**Who:** a GitHub organization admin (or a repository admin), signed in to `gh`.

Uses `tenant_id`, `subscription_id`, `github_repo`, `apply_approvers`, and `pipeline_client_id` from step 4.

```bash
python3 scripts/setup.py github          # read it
python3 scripts/setup.py github --run
```

It sets the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`, creates the labels `allow-risky-changes` and `drift`, the environment `apply-approval` (deployments from `main` only; with `apply_approvers` set, that team must approve each apply), and protects `main`: pull requests only, the **Format and validate** and **Tests** checks must pass, and code owners must approve. The rule applies to **repository admins too**: a push to `main` is an apply with workspace admin rights, so nobody can skip the review. A pull request needs an approval from someone other than its author, so name at least two people in each code owner team. A push after an approval dismisses it, so what merges is what was reviewed.

Then, if needed:

- **Private networking.** If the workspaces use Private Link or an IP access list, GitHub-hosted runners cannot reach them. Register a self-hosted runner inside the network (or use GitHub's Azure private networking) and set the repository variable `TERRAFORM_RUNNER`, for example `"citizen-dev"` with the quotes; if your organization has no GitHub-hosted runners at all, set `CHECKS_RUNNER` too ([docs/github-actions.md](github-actions.md): what the runner needs and must reach).
- **Write access.** Only the platform team should be able to push branches: a pull request's plan runs with the pipeline's workspace-admin rights before review ([docs/github-actions.md](github-actions.md), "Who can run code with the workspace credentials").

> **Warning:** Required reviewers and branch protection need GitHub Team or Enterprise for private repositories. Without them, merging is the only approval and nothing stops a merge before its plan finishes: wait for every check first.

## 6. Databricks account (by hand)

**Who:** a Databricks account admin, in the account console (https://accounts.azuredatabricks.net). Once, before the first workspace; items 2 and 5 again for each new workspace (item 5 needs a metastore admin). You need the service principal's client ID, `pipeline_client_id` in `config/setup.yaml` (step 4 writes it).

1. **Add the service principal to the account:** User management > Service principals > Add service principal > **Microsoft Entra ID managed**, with the application ID `pipeline_client_id` and the name `pipeline_name` (default `sp-citizen-dev-terraform`).
2. **Make it workspace admin** of each workspace this repository manages: Workspaces > the workspace > Permissions > Add permissions > the service principal, **Admin**.
3. **Let it create serverless usage policies** (their API still calls them budget policies): in the account console, User management > Service principals > the service principal > Roles, turn on **Billing admin**. Account admin alone is not enough ("missing CreateBudgetPolicyPermission"). If you will not grant this, set `serverless_policy.enabled: false` in `config/defaults/cost.yaml` instead.
4. **Note the account ID** (account console, top right) for `account_id` in `config/defaults/cost.yaml` (step 8): usage policies belong to the account.
5. **Let it create the workspace catalog.** A **metastore admin** of each workspace's metastore grants, in a SQL editor or Catalog Explorer (the metastore > Permissions):

   ```sql
   GRANT CREATE CATALOG ON METASTORE TO `<pipeline_client_id>`;
   ```

   A workspace that Databricks enabled for Unity Catalog automatically may already give its workspace admins this privilege, and with it the pipeline (item 2); preflight tells you. The catalog also needs somewhere to keep its data: either the metastore has a storage root, or the workspace's file sets `catalog.storage_root` to an external location (the Unity Catalog team creates the storage credential and external location). In that case, also grant `CREATE MANAGED STORAGE` on that external location to the service principal.

   **A catalog that already exists** (from an earlier setup) must be owned by the service principal, or later applies cannot change it or its grants. If a group owns it, a metastore admin runs `ALTER CATALOG <name> OWNER TO \`<pipeline_client_id>\``; preflight names it.

The service principal is never account admin or metastore admin: it needs workspace admin in the workspaces it manages, Billing admin (for the serverless usage policy) and `CREATE CATALOG`. It owns the catalog it creates, which is what lets later applies change it; the platform admins group gets all privileges and `MANAGE` on it (`config/defaults/catalog.yaml`). `scripts/preflight.py` (step 9) confirms items 2, 3 and 5 for each workspace.

## 7. Groups

**Who:** the identity team.

Create Entra ID groups and sync them to the Databricks account (automatic identity management or SCIM provisioning). They must be **account groups**: Unity Catalog grants and usage policies cannot use groups created inside a workspace. Terraform assigns them to the workspace; it never adds people. Who is in each group stays in Entra ID.

| Group | Named | Gets |
| --- | --- | --- |
| Platform admins | `{prefix}_platform_admins`, one per workspace prefix (the baseline) | Workspace admin; all privileges and MANAGE on the workspace catalog |
| Users | Per workspace, in its file (`groups.users`) | Consumer access (Databricks One): dashboards, Genie spaces, apps |
| Explorers | Per workspace (`groups.explorer`) | SQL access: the SQL editor, queries, dashboards, Genie |
| Builders, publishers | Per workspace (`groups.builder`, `groups.publisher`) | Workspace access: notebooks, jobs, pipelines on serverless; classic compute only through the self-service app |

A workspace that leaves a persona's group `null` simply has nobody with that persona.

Put the workspace's platform team in `{prefix}_platform_admins`: it manages the workspace's serverless usage policy and the catalog, and nobody outside the policy's groups can see the policy (workspace admin is not enough). Preflight warns while the group is empty.

> **Tip:** Groups created in the Databricks account instead of Entra ID (a test account, for example) can be managed there: to let the platform admins add and remove members, open each persona group in the account console > **Permissions** and give `{prefix}_platform_admins` **Manage**. Do not do this for groups synced from Entra ID: the next sync overwrites members changed in Databricks. Terraform does not manage group managers.

## 8. Decide the baseline

The baseline in `config/defaults/` is what every workspace gets. Most of it is a sensible default; these settings need a decision before the first apply, because they are hard to undo or depend on your organization. Change them in a pull request (or before the first push).

| Decision | File and key | Shipped value | Notes |
| --- | --- | --- | --- |
| **Disable legacy access** (Hive metastore, No-isolation clusters) | `defaults/settings.yaml` `disable_legacy_access` | `true` | **One-way after 30 days.** Fine for new workspaces. For an existing one, `preflight.py` lists what still uses legacy access; set it to `null` under `settings:` in that workspace's file until it is migrated |
| DBFS root and mounts off, user isolation enforced | `defaults/settings.yaml` `disable_dbfs_root_and_mounts`, `enforce_user_isolation` | `true` | Reversible, but they break the same legacy work: leave them `null` with `disable_legacy_access` for a workspace that is not migrated yet |
| **Default catalog** | `defaults/catalog.yaml` `default_catalog` | `{prefix}_citizen_dev` (the workspace's own catalog) | Unqualified table names resolve to it instead of the catalog Databricks created with the workspace. The plan guard flags it on each workspace's first plan; `null` leaves the default alone |
| Git URLs allowed in Git folders | `defaults/settings.yaml` `git.allowed_urls` | `https://github.com/` (every github.com repository; other Git hosts blocked) | Narrow it to your organization (`https://github.com/<your-org>/`), or add your GitHub Enterprise host |
| Compliance security profile | `defaults/settings.yaml` `compliance_security_profile` | `null` (leave alone) | **One-way**, and billed. Only if your compliance team requires it |
| Unity Gateway enforced | `defaults/settings.yaml` `enforce_unity_gateway` | `true` | Switches off the `databricks-` pay-per-token endpoints; model calls must use `system.ai` models |
| Collaboration platforms | `defaults/settings.yaml` `collaboration_platforms.allowed` | `ALLOW_TEAMS` | `ALLOW_ALL`, `ALLOW_SLACK`, `ALLOW_TEAMS` or `DENY_ALL` |
| Dashboard embedding domains | `defaults/settings.yaml` `dashboard_embedding.approved_domains` | none | For example your SharePoint domain |
| Personal access tokens | `defaults/settings.yaml` `personal_access_tokens`, `defaults/access.yaml` `personas.<persona>.can_create_tokens` | On, 90 days, no persona may create them | Only admins create tokens unless a persona is allowed |
| Platform admins group name | `defaults/access.yaml` `groups.platform_admins` | `{prefix}_platform_admins` | Match your Entra naming convention; `{prefix}` is the workspace's prefix. Persona groups are named per workspace |
| Databricks account | `defaults/cost.yaml` `account_id` | none | Required while the serverless usage policy is on (account console, top right) |
| Chargeback tags | `defaults/cost.yaml` `tags`, `classic_user_tags` | `BUSINESS_UNIT` (from `prefix`), `APPID: NONE`, `COST_CATEGORY: CITIZEN_SELF_SERVICE`; users fill in `APPID`, `TEAM`, `PROJECT` on classic clusters | One list, on the usage policy, the warehouse and classic clusters. Each workspace sets its own `APPID` (`tags:` in its file). Changing them later affects new usage only |
| Serverless usage policy | `defaults/cost.yaml` `serverless_policy` | On, `{PREFIX}-0-SELF-SERVICE`, every persona | Needs an account-level permission for the pipeline (step 6); set `enabled: false` if you will not grant it. Data classification (turned on by hand, step 9) uses it |
| Catalog name and features | `defaults/catalog.yaml` `catalog` | `{prefix}_citizen_dev`, predictive optimization on | `catalog.storage_root` is needed when the metastore has no storage root (preflight says so) |
| Serverless Starter Warehouse | `defaults/compute.yaml` `starter_warehouse.admins_only` | `true` | Only the platform admins may use the Starter warehouse Databricks creates in a new workspace; on an existing one, **anyone using it loses access** on the first apply. `null` leaves its access alone |
| `/Workspace/Shared` | Not managed | Databricks gives `users` Can manage | Anyone can read and change what is shared there; data access is still decided by Unity Catalog. Remove `users` by hand if folder permissions should mean something (`docs/design.md`, open question P12) |
| Classic cluster node types | `defaults/compute.yaml` `cluster_policy.node_types` | `Standard_E8_v3`, `Standard_E16_v3`, `Standard_E32_v3` | Azure VM sizes: check they are offered in your workspaces' region and that the subscription has quota |
| Restrict workspace admins | `defaults/settings.yaml` `restrict_workspace_admins` | `false` | Needs account admin to change; leave `false` |
| AI review of each plan | `config/setup.yaml` `ai_review_host`, `ai_review_model` | Off until a host is set; then `system.ai.claude-sonnet-5-5` there | Advice in the plan comment only. One workspace that has the model reviews every plan; the pipeline's service principal needs to be in it, with `EXECUTE` on the model (account users have it on `system.ai` by default) |

What each setting does is in the comment beside it, and in [config/README.md](../config/README.md).

## 9. Onboard a workspace

**Who:** the platform team. Repeat for every workspace. Step by step, with what you see at each point: [user-journeys.md](user-journeys.md), journey 1.

Before you start: the workspace exists and the runners can reach it (its private endpoint and DNS), the pipeline's service principal is workspace admin there (step 6, item 2), and its persona groups exist in Entra ID (step 7). In a **brand-new workspace**, a workspace admin also creates one personal access token (Settings > Developer > Access tokens > Generate new token) and revokes it straight away: Databricks creates the workspace's token permissions with the first token, and until then Terraform cannot set who may create tokens. Once per workspace; preflight says if it is needed.

1. **Create its file:** copy `config/workspaces/_example.yaml` to `config/workspaces/fin-citizen-dev.yaml` and fill in `prefix`, `host` and `groups`. The file name is the workspace's name in this repository.
2. **Set anything that differs from the baseline**, in the same file (for example `catalog.storage_root`, or `null` for `settings.disable_legacy_access`, `disable_dbfs_root_and_mounts` and `enforce_user_isolation` for an existing workspace that is not ready). Leave the rest out.
3. **Check it is ready** (optional; the pull request runs it too). It uses the Databricks CLI: sign in with `az login` (used automatically for Azure workspaces), or set a Databricks CLI profile in the workspace's file (`auth.workspace_profile`):

   ```bash
   python3 scripts/preflight.py fin-citizen-dev
   ```

   It checks the sign-in and admin rights, the metastore, that every group is an account group (and that the platform admins group has members), that the pipeline may create usage policies (Billing admin), that it may create the catalog (or owns it), the catalog's storage, that the workspace has token permissions, and what still uses legacy access.
4. **Open a pull request.** The deploy workflow plans only this workspace and posts its plan: everything the first apply creates. Preflight problems are at the top of the comment.
5. **Approve the first plan.** A new workspace's first plan is always flagged by the plan guard: it sets the default catalog and makes the Starter warehouse admins only. A platform team member who has read the plan comment adds the `allow-risky-changes` label (see **Approving a flagged change**, step 10); the plan check then re-runs and passes.
6. **Merge only when every check is green, including Plan.** Only **Format and validate** and **Tests** are required by branch protection (the plan jobs' names change with the workspaces), so GitHub lets you merge past a red plan; the apply would then stop at the same problem: a preflight problem before anything changes, a problem only Terraform finds partway. After the approval step (if `apply-approval` has reviewers), the workspace is deployed.
7. **Verify:** the next pull request that touches it (or the Monday drift check) shows no changes. In the workspace: the persona groups under Settings > Identity and access, the `<PREFIX> Default Warehouse`, and the `{prefix}_citizen_dev` catalog.
8. **By hand, in Catalog Explorer** (`{prefix}_citizen_dev` > Details), as a member of `{prefix}_platform_admins`: turn on **Data Classification**, with the workspace's usage policy `<PREFIX>-0-SELF-SERVICE`, and **Data Quality Monitoring** for each schema the self-service app created. Terraform does not manage either (classification's API needs a usage policy the Terraform provider cannot send; monitoring is per schema, and schemas come from the self-service app). Turn monitoring on again for schemas created later.
9. **By hand, in Workspace settings > Appearance:** the workspace theme's categorical colors and the Genie One (the Genie home page) color and welcome message, with the values in `config/defaults/settings.yaml` ("Appearance: set by hand"). There is no API for them yet.

> **Warning:** Applying the baseline to an existing workspace changes its settings for everyone in it (downloads, tokens, Git folders, legacy access). Read the plan comment's settings changes with the workspace's owners before merging.

## 10. Day to day

| Task | How |
| --- | --- |
| Give someone a persona | Add them to the group in Entra ID; no change here |
| Change one workspace | Pull request editing `config/workspaces/<name>.yaml`: only that workspace is planned and applied |
| Change every workspace | Pull request editing `config/defaults/`: every workspace is planned, and applied, each in its own job (one that fails does not stop the others) |
| Retire a workspace | Delete its file in a pull request: its Terraform state is removed on merge; the workspace itself is unchanged |
| A plan is flagged as risky | **Approving a flagged change**, below |
| A `drift` issue opens | Someone changed a setting by hand: update the configuration to match, or re-apply to restore it |
| Retry a failed apply | Fix the cause, then re-run the latest Apply run (it refuses if `main` has moved on) |
| Plan locally | `./scripts/tf.sh <name> plan`, signed in with `az login`. You need **Storage Blob Data Contributor** on the state container (a local plan takes the state lock, which writes), and Databricks access to the workspace. CI's plan is the one to trust |
| Upgrade to a new release | Below: the pull request's plan shows what the new version changes in each workspace |

More: [config/README.md](../config/README.md) (configuration tasks) and [github-actions.md](github-actions.md) (the workflows).

### Approving a flagged change

The plan guard flags changes that are hard to undo or that weaken security or take access away (the list: [design.md](design.md), section 3). A flagged plan fails its check until the pull request has the label `allow-risky-changes`.

1. **Read the plan comment**: the guard's findings are under **Before merging** and **Technical details**. The AI review says what they mean for the workspace.
2. **A platform team member other than the author** adds `allow-risky-changes` (the pull request's Labels, in the sidebar), only if the change is intended. The plan check re-runs and passes. The label records the approval; it does not make the change safer.
3. **The apply checks it again:** a flagged change merged without the label stops at apply. Add the label to the merged pull request, then re-run the apply.

> **Warning:** Anyone with write access can add a label, and GitHub cannot limit labels to a team. Keep write access to the platform team, and require code owner review (step 5). For a second pair of eyes on every deploy, set `apply_approvers` in `config/setup.yaml`: each apply then waits for that team in the `apply-approval` environment.

A new workspace's first plan is always flagged (the default catalog, the Starter warehouse). Disabling legacy access is not flagged there when preflight found nothing that still uses it.

### Upgrade to a new release

Each release is a zip named after its version (`v1.2.0`), with what changed in `CHANGELOG.md`. `VERSION` at the top of the repository says which release you run.

Replace the framework files, keep your configuration. Unpack the new release next to your repository (for example as `../new`), then from your repository:

```bash
FRAMEWORK="terraform scripts .github/workflows .github/actions .github/scripts .github/ai docs \
  .github/dependabot.yml .github/pull_request_template.md README.md CHANGELOG.md AGENTS.md CLAUDE.md \
  agents config/README.md config/AGENTS.md config/workspaces/_example.yaml VERSION"
git rm -r -q --ignore-unmatch $FRAMEWORK             # also drops files the release removed
(cd ../new && tar -cf - $FRAMEWORK) | tar -xf -      # the release's versions
git add -A && git checkout -b upgrade-v1.3.0
```

It touches nothing else: not `config/defaults/`, your workspaces, `config/setup.yaml` or `.github/CODEOWNERS`. A baseline setting that is new in the release is absent from your `config/defaults/` until you add it, which means "leave alone", so an upgrade never turns something on by itself. Each release's **Baseline edits** in `CHANGELOG.md` lists the YAML to change in `config/defaults/`: new settings, and defaults the release changed that you may want too. Open a pull request: its plan shows what the new version changes in each workspace before anything is applied.

> **Warning:** Do not edit framework files in your repository: the next upgrade replaces them. Send a fix to the framework maintainers so it is in the next release.

### State and teardown

State is local (`.state/<name>.tfstate`) unless `config/backend.hcl` exists (step 3 writes it); then each workspace has its own state file in Azure Storage, which CI requires.

**To stop managing a workspace, retire it** (delete its file in a pull request): Terraform forgets it, and nothing in the workspace changes.

`./scripts/tf.sh <name> destroy` is different: it **deletes** what this project created, including the default warehouse, the usage and cluster policies, and the workspace catalog **with its data**, and resets the workspace configuration keys it manages (`enable*`, `enforce*`) to `false`, which turns personal access tokens off. Outside GitHub Actions it refuses unless `ALLOW_LOCAL_APPLY=1` (see **Break glass**, step 11). Review the plan before confirming.

## 11. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No matching federated identity record found for presented assertion` (an `AADSTS` error at sign-in) | The token's subject is not one of the two credentials: the repository was renamed or transferred, or a workflow ran from a branch other than `main` (Drift or Apply run by hand on a branch) | Update `github_repo` in `config/setup.yaml` and run step 4 again (it reads the current subject prefix); run Apply and Drift only from `main` |
| `Source IP address ... is blocked by Databricks IP ACL`, or a timeout reaching the workspace | GitHub-hosted runners cannot reach the workspace | A runner inside the network and `TERRAFORM_RUNNER` (step 5) |
| `AuthorizationPermissionMismatch` or `403` reading the state | The role on the state container is missing or still propagating | Wait a few minutes after step 4; check Storage Blob Data Contributor on the container |
| `state blob is already locked` | Another apply, or a local plan, holds the lock (CI plans do not lock) | If an apply for the workspace is running (the repository's Actions tab), wait for it and re-run. If none is, see **A lock left by a run that died**, below |
| An apply was cancelled or timed out partway | The changes before the stop are made and in the state; the rest are not | Re-run the apply: Terraform makes only what is left. If it says the state is locked, see below |
| Preflight: `is not a workspace admin` | Step 6 not done for this workspace | Step 6, item 2, for this workspace |
| Preflight: group `does not exist in the account` or `exists only in this workspace` | The Entra group is missing, not synced, or a workspace-local group has the same name | Step 7; or name the right group under `groups:` in the workspace's file |
| Preflight: `the metastore has no storage root` | New catalogs have nowhere to store data | Set `catalog.storage_root` in the workspace's file to an external location URL |
| Preflight: `cannot create catalog`, or the apply fails with `PERMISSION_DENIED` creating the catalog | The service principal lacks `CREATE CATALOG` on the metastore, or `CREATE MANAGED STORAGE` on the external location of `catalog.storage_root` | Step 6, item 5 |
| Preflight: `does not own catalog`, or the apply fails with `PERMISSION_DENIED` updating the catalog or its grants | Someone else owns the catalog (it existed before, or `catalog.owner` handed it to a group the pipeline is not in) | A metastore admin runs `ALTER CATALOG <name> OWNER TO \`<pipeline_client_id>\``, and `catalog.owner` stays `null` |
| Preflight: `never had a personal access token`, or the apply fails with `cannot create permissions: tokens tokens does not exist` | A brand-new workspace: Databricks creates its token permissions with the first token | A workspace admin creates one token and revokes it straight away (step 9), then re-run the plan or the apply. An apply that stopped here made everything before it; the re-run makes the rest |
| A workspace was retired by mistake | Merging the deletion of its file deleted its Terraform state | Restore `citizen-dev/<name>.tfstate` from an earlier blob version in the state container (blob versioning, step 3: in the Azure portal, the container > Show deleted blobs > the blob > Versions > Make current version), then restore the workspace's file in a pull request |
| Preflight: `cannot create the workspace's serverless usage policy`, or the apply fails with `missing CreateBudgetPolicyPermission` | The service principal lacks the account's **Billing admin** role (account admin alone is not enough) | Step 6, item 3, or `serverless_policy.enabled: false` |
| `setup.py github` fails at branch protection: `Upgrade to GitHub Pro or make this repository public` | Branch protection on a private repository needs a paid GitHub plan | The rest of step 5 is done. Protect `main` by hand once the plan allows it; until then, merging is the only review |
| Apply: `the merged pull request has no allow-risky-changes label` | The plan guard flagged the change, and it was merged without the label | If a person approves it, add the label to the merged pull request and re-run the apply; otherwise revert the change in a new pull request |
| A local plan shows permission changes that CI does not | Local plans run as you, not the pipeline: the owner entry differs | Trust the CI plan and the drift check |
| The plan comment has no AI review | `ai_review_host` is not set, the service principal is not in that workspace, or the model is unavailable to it there (region, Unity Gateway, missing EXECUTE) | Set `ai_review_host` to a workspace that has the model, add the service principal to it, or change `ai_review_model`; the review is advice only |
| Apply ran straight after the merge, without approval | `apply-approval` has no required reviewers (or the GitHub plan does not support them) | Add reviewers to the environment (`apply_approvers`, then step 5 again) |

### A lock left by a run that died

An apply takes a lock on its workspace's state, and releases it when it ends. A runner that is killed partway (cancelled, timed out, the machine lost) can leave it behind, and every later apply for that workspace fails with `state blob is already locked`.

1. **Make sure nothing is running.** In the repository's **Actions** tab, no Deploy run for the workspace is in progress, and nobody is running `tf.sh` locally. Releasing the lock of a running apply corrupts the state.
2. **Copy the lock ID** from the error (`ID: 1a2b3c4d-...`). It also says who took the lock and when.
3. **Release it**, signed in with the Azure CLI as someone with **Storage Blob Data Contributor** on the state container:

   ```bash
   ./scripts/tf.sh <name> force-unlock <lock ID>
   ```

   Without a terminal: in the Azure portal, the state container > `citizen-dev/<name>.tfstate` > **Break lease**.
4. **Re-run the apply** (the failed run's **Re-run jobs**, or the latest run on `main`). Terraform finishes what the stopped run did not.

If the state itself is damaged (an apply reports it cannot read it), restore the last good version: the container > the blob > **Versions** > **Make current version**, then re-run the apply.

### Break glass: applying from a laptop

For when CI cannot run (GitHub is down, the runner is broken) and a workspace needs a fix now. Everything else goes through a pull request.

1. **Use the shared state.** `config/backend.hcl` must be in your checkout: `tf.sh` refuses to apply without it, because a local state would split from the one CI uses.
2. **Sign in as someone with the pipeline's rights:** workspace admin in the workspace, Storage Blob Data Contributor on the state container, and for usage policies the account's Billing admin role (step 6). A local run uses your identity, not the service principal.
3. **Plan, then apply** from `main` with the fix on top:

   ```bash
   ./scripts/tf.sh <name> plan
   ALLOW_LOCAL_APPLY=1 ./scripts/tf.sh <name> apply
   ```

   The apply takes the same lock CI does, so it cannot run at the same time as a CI apply.
4. **Open a pull request with the same change straight after.** Until it is merged, `main` does not match the workspace, and the next CI apply or drift check undoes the fix.
