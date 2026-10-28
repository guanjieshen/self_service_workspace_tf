# Citizen Development Workspace Baseline: Design

What this project does, how it is built, and why. The operating guide (how to change
the configuration) is [config/README.md](config/README.md); CI setup is
[docs/github-actions.md](docs/github-actions.md); ideas not built yet are in
[docs/future.md](docs/future.md).

## 1. Purpose

Every citizen development workspace gets the same governed baseline: secure admin
settings, three personas with fixed rights, compute people can use straight away, one
Unity Catalog catalog with personal schemas on request, and chargeback tags. The
platform team runs it from Git: YAML only, reviewed in pull requests, applied by CI.

**In scope:** the configuration of an existing workspace (settings, personas, compute,
the workspace catalog, budget policies, Genie Code), the jobs that create per-person
and per-team objects on request (personal schemas, team folders), run by workspace admins
or the service principals in `jobs.runners` (a ticketing system, or a self-service app
built on top). The jobs are the interface for anything that automates requests.
**Out of scope:** creating workspaces and networking (combined mode, future), the
metastore and shared catalogs, who is in which group (Entra ID), and a request portal.

## 2. How it works

```
 Entra ID groups (synced to the account)          config/  (YAML, reviewed in pull requests)
 {bu}_users  {bu}_explorer  {bu}_builder  ...        defaults/          one baseline for every workspace
        │   membership: Entra                        workspaces/<name>/ one folder per workspace
        │                                                 │
        ▼                                                 ▼
 ┌─────────────────────────── Terraform, one state per workspace ───────────────────────────┐
 │ settings │ entitlements │ warehouse, cluster, policies │ catalog + grants │ budget policies │
 │ Genie Code │ the on-request jobs: personal schemas, team folders                            │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
        │                                                 │
        ▼                                                 ▼
 the jobs, run by admins or jobs.runners          CI: plan on every pull request (plan guard,
 (cd_<name> schemas, team folders)              AI review), apply on merge, weekly drift check
```

Everything is granted to **groups**, never to people. Adding someone to `{bu}_builder` in
Entra ID gives them everything a builder gets, with no change to this repository and no
Terraform run. The only per-person objects, personal schemas, and team folders come
from jobs that this repository deploys and admins (or the service principals in
`jobs.runners`) run.

## 3. Configuration model

One rule: **a workspace changes a default by setting the same key in its file of the
same name** (`config/workspaces/<name>/settings.yaml` over `config/defaults/settings.yaml`,
and so on for `access`, `compute`, `cost`, `catalog`). Maps merge key by key, a list or
value replaces, and `null` means "Terraform leaves this alone". A key the baseline does
not have fails the plan with its name, so a typo cannot silently do nothing. A few keys
exist only in a workspace's files: `workspace.yaml` (identity), `teams`, `team_warehouses`.
See config/README.md for the files and a task table.

**Leaving a setting alone releases it.** On a workspace that was already applied, a
setting set to `null` (or a `manage` switch set to `false`) is removed from Terraform's
state before apply (`scripts/tf.sh`), so the workspace keeps its current value. It is
never destroyed, because destroying a setting resets it: the provider erases a workspace
configuration key that leaves Terraform (`enableTokensConfig` would become `false`,
switching off every personal access token), and a deleted setting returns to the
platform default. `terraform/overrides.tf` maps each setting to what it owns.

**Governance is in the pull request, not the code.** Any default can be changed for one
workspace. What keeps that safe:
- **Plan guard** (`scripts/plan-guard.py`) fails the check when a plan deletes or
  replaces something people depend on (folders, warehouses, clusters, policies, budget
  policies, permissions, grants, catalogs), or weakens security (a setting turned off,
  deleted or loosened, a catalog opened to every workspace, a grant to everyone, more
  token creators), until someone adds the label `allow-risky-changes`.
- **The AI review** in the plan comment lists every deviation from the baseline, old and
  new value, security-relevant ones first.
- **Code owners** decide who approves which files.

## 4. Access model

**Groups.** One account group per role, named from a pattern in
`config/defaults/access.yaml` (a workspace can rename one):

| Group | Entitlement | Default warehouse | Shared cluster | Cluster policy | Usage policy | Catalog |
|---|---|---|---|---|---|---|
| `{bu}_users` (everyone) | Consumer (Databricks One) | | | | | |
| `{bu}_explorer` | SQL access | Can use | | | User | USE CATALOG, USE SCHEMA; own schema |
| `{bu}_builder` | Workspace and SQL access | Can use | Can attach to | One cluster per person | User | same |
| `{bu}_publisher` | Workspace and SQL access | Can use | Can attach to | One cluster per person | User | same |
| `{bu}_platform_admins` | Workspace admin | Manage | Manage | Manage | Manager | Owner; all privileges |

- Entitlements are tiers, each including the one before: Consumer access (Databricks One
  only) < SQL access (plus the SQL editor, queries, dashboards and Genie) < workspace
  access (the full workspace). A group gets the highest tier any of its personas has;
  the provider accepts Consumer access only on its own, so the module sets it only then.
- Builders and publishers can attach to the shared cluster but not start, restart or change it:
  when it has stopped (60 idle minutes), a platform admin starts it.
- Nobody gets "Allow unrestricted cluster creation". No persona is workspace admin:
  persona groups join the workspace as users; only the platform admins group as admin.
- Builder and publisher are the same here; what makes a publisher different is handled
  outside this project.
- The groups must be **account groups** (Entra ID groups synced to the account). Unity
  Catalog and usage policies cannot use groups that exist only in a workspace
  ([docs](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/workspace-local-groups)).
  The test workspaces use workspace-local groups, so they leave group assignment,
  catalog grants and budget policies alone.

**Requests.** Two paths, by volume and risk:

| Request | Path |
|---|---|
| A persona (explorer, builder, publisher) | The person asks in Entra (for example an access package), which adds them to the group. No pull request |
| A personal schema (one per person), a project schema (a name they choose) or a team schema (a name and one of their groups) | An admin or a runner runs the `<BU> personal schema` job (Terraform deploys it) with the user, catalog and, for a custom one, the name. No pull request |
| A workspace folder | An admin or a runner runs the `<BU> team folder` job (Terraform deploys it) with the folder name, the requester and, optionally, a group of theirs that owns it too. No pull request |
| A team warehouse, shared schema or extra grant | A person writes a file under `config/workspaces/<name>/` and opens a pull request: plan, AI review, approval, apply |

## 5. The workspace catalog and personal schemas

Each workspace gets one catalog, `{bu}_citizen_dev` (`config/defaults/catalog.yaml`),
bound to the workspace and owned by the platform admins group, with predictive
optimization, data classification and data quality monitoring on.

- **Catalog-level grants are minimal.** Personas get `USE CATALOG` and `USE SCHEMA`:
  enough to reach a schema and use what was shared with them, never data catalog-wide,
  and no `CREATE SCHEMA`. Data access is per schema.
- **Shared schemas** are listed in `catalog.yaml` with their grants (a grant's principal
  can be a persona name); Terraform creates them and turns on data quality monitoring.
- **Personal schemas** come from the job `<BU> personal schema`, a short notebook
  (`terraform/modules/catalog/personal_schema.py`) that Terraform deploys. An admin,
  or a runner in `jobs.runners`, runs it when a user asks; there is no schedule.
  - **Parameters:** `user` and `catalog` (both required; the catalog must be an allowed
    one), `schema` (default `cd_` plus the email before the `@`, everything but letters
    and digits replaced by `_`: `jane.doe@…` → `cd_jane_doe`) and `request_id`.
    No parameter has a default: each run sets them.
    Prefix, privileges, owner and the allowed catalogs come from `catalog.yaml`: Terraform
    writes them into the notebook, so a run cannot change them (a run can pass any
    parameter, even ones the job does not define, so they cannot be parameters).
  - **Steps:** create the schema if it does not exist, tag it (`cd_managed_by =
    self_service`, `cd_user`, `cd_created`, `cd_request_id`), grant the user
    `ALL_PRIVILEGES` and `MANAGE` (so they can share it themselves), and give it to the
    platform admins group.
  - **Checks:** only workspace admins, and the service principals in `jobs.runners`
    (for example a ticketing system's), can see and run the job, and the notebook checks
    each request. An existing schema must already be
    tagged with the same `cd_user`, so a request never gets another person's schema or
    a shared one.
  - **State:** the tags on each schema, which callers (and audits) can query in
    `information_schema.schema_tags`. Running it again for the same user is safe.
  - **Notebook location:** the admin folder (`folders.admin`, `/Admin/self-service`), at
    the top of the workspace, which grants only workspace admins: the job runs with the
    rights to manage the catalog, so only admins may change the notebook. The team folder
    job's notebook is there too.
  - A catalog holds 10,000 schemas by default (it can be raised); enough for a BU.

## 6. Caveats

1. **Disabling legacy access can become permanent** after 30 days. Before applying to an
   existing workspace, check nothing uses Hive tables, DBFS mounts or No-isolation
   clusters; until then set `disable_legacy_access: null` in its `settings.yaml`.
2. **Terraform owns what it manages.** Entitlements, permissions, grants and budget
   policy access are authoritative: changes made by hand are reverted on the next apply
   (the drift check reports them first).
3. **Budget policies tag usage; they do not cap spend.** A user with several policies who
   does not choose gets the first alphabetically. They need an account-level permission
   for the CI identity; without it, set `budget_policies.enabled: false`.
4. **The SQL statement timeout** manages the workspace-wide SQL configuration as a whole.
5. **Enforce Unity Gateway** switches off the `databricks-` pay-per-token endpoints;
   model calls must use `system.ai` model services.
6. **Team folders are private to their team; `/Workspace/Shared` is open to all.** Team
   folders sit at the top of the workspace (`/Workspace/<team>`), which inherits only
   admins, so only the team's group (and admins) can reach one. `/Workspace/Shared`
   grants `users` Can manage. Data access is still decided by Unity Catalog.
7. **Data classification needs a usage policy.** It runs on serverless; the identity
   running Terraform must be able to use a serverless usage policy, or turning it on fails
   with "Usage policy ID must not be empty". Workspaces without usage policies set
   `catalog.data_classification: null`.
8. **Provider workaround:** `effective_workspace_label` is set to the label too (provider
   1.137.0 declares it optional instead of computed, which failed the apply).

## 7. Repository layout

```
config/            the organization's configuration (config/README.md)
  defaults/        access, compute, cost, catalog, settings .yaml; genie-code/
  workspaces/      one folder per workspace; _example/ is the template
  ai-review.yaml   the AI review's model
terraform/         root module (config.tf loads and merges the YAML, overrides.tf what a
                   workspace may set and what leaving alone releases, access.tf groups and
                   grants, chargeback.tf budget policies,
                   checks.tf plain-language checks)
  modules/         workspace-settings, personas, compute, budget-policies, folders, catalog
  tests/           Terraform tests with mocked providers and fixture workspaces
scripts/           setup.py (one-time setup), preflight.py (is a workspace ready), tf.sh
                   (run Terraform), plan-guard.py, workspaces.py (new, changed,
                   check), ai-plan-review.py, test.sh
.github/           plan, apply and drift workflows; the AI review prompt; CODEOWNERS
dev/workspaces/    the framework's own test workspaces (not in a release)
```

Releases are git tags; install and upgrade with git (README.md).

## 8. Testing

`./scripts/test.sh` runs every suite without a workspace or credentials, as the **Tests**
check on every pull request does: Terraform tests against mocked providers (baseline,
options, modules, Genie Code, and one fixture per validation check), Python unit tests
(plan guard, release, workspaces, the AI review, the personal schema and team folder
jobs), the plan comment (Node), and a scaffolded workspace. A new option comes with a fixture and an
assertion; a new check with a fixture that fails it. Before a change merges, its plan on
the test workspaces in `dev/` shows what it does.

## 9. Open questions

| # | Question | Default until decided |
|---|---|---|
| A1 | Restrict serverless egress (account network policy)? | Not managed |
| A2 | Private endpoints from serverless to the organization's storage? | Not managed |
| A3 | Budget alerts per BU (account-level)? | Not managed |
| A4 | Audit log delivery to the SIEM? | Not managed |
| A5 | Personal Compute account setting: Delegate? (With On, every user can create personal clusters outside the persona policies) | Not managed |
| S1 | Compliance security profile (one-way) or enhanced security monitoring? | Neither |
| S2 | Automatic cluster updates, and the window? | Not managed |
| S3 | Verbose audit logs (only useful with A4)? | Not managed |
| S4 | Interactive notebook results in the workspace's own storage? | Not managed |
| P5 | Approved dashboard embedding domains? | None |
| P7 | GitHub org URL for the Git allowlist? | Placeholder |
| P8 | Required tag keys (LOB, DEPARTMENT, TEAM)? | As is |
| P12 | Remove `users` from `/Workspace/Shared` so folder permissions mean something? | Organisation only |
| R1 | Who removes the personal schemas of people who left, and after how long? | Out of scope |
