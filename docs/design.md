# Design

Why the project works the way it does. How to set it up is [SETUP.md](SETUP.md); how to
change the configuration is [config/README.md](../config/README.md); the workflows are
[github-actions.md](github-actions.md).

> **Reading this to change the framework?** Read it with [AGENTS.md](../AGENTS.md), which says what to change together and how to test it.

## 1. Purpose

Every citizen development workspace gets the same governed baseline: secure admin
settings, three personas with fixed rights, compute people can use straight away, one
Unity Catalog catalog, and chargeback tags. The
platform team runs it from Git: YAML only, reviewed in pull requests, applied by CI.

**In scope:** the configuration of an existing workspace (settings, personas, compute,
the workspace catalog, the chargeback tags and serverless usage policy, Genie Code).
**Out of scope:** creating workspaces and networking (combined mode, future), the
metastore and shared catalogs, who is in which group (Entra ID), and everything people
request: schemas (the self-service app today; workspace folders are coming), and team warehouses,
project usage policies and access to classic compute (by hand until the app offers them). The rule: Terraform holds what every workspace has
and rarely changes; anything that changes by ad hoc request belongs to the app.

## 2. How it works

```
 Entra ID groups (synced to the account)          config/  (YAML, reviewed in pull requests)
 one group per persona, per workspace              defaults/          one baseline for every workspace
        │   membership: Entra                        workspaces/        one file per workspace
        │                                                 │
        ▼                                                 ▼
 ┌─────────────────────────── Terraform, one state per workspace ───────────────────────────┐
 │ settings │ entitlements │ warehouse, cluster policy    │ catalog + grants │ usage policy    │
 │ Genie Code                                                                                │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
                                                          │
                                                          ▼
                                                  CI: plan on every pull request (plan guard,
                                                  AI review), apply on merge, weekly drift check
```

Everything is granted to **groups**, never to people. Adding someone to a workspace's
builder group in Entra ID gives them everything a builder gets, with no change to this
repository and no Terraform run.

## 3. Configuration model

One rule: **a workspace is one file, `config/workspaces/<name>.yaml`, and it changes a
default by setting the same top-level key as the baseline** (every key is defined in exactly
one file of `config/defaults/`). Maps merge key by key, a list or
value replaces, and `null` means "Terraform leaves this alone". A key the baseline does
not have fails the plan with its name, so a typo cannot silently do nothing. A few keys
exist only in a workspace's file: `prefix`, `host`, `label`, `genie_code_instructions`, and rarely `auth` and `id`.
See config/README.md for the files and a task table.

**Leaving a setting alone releases it.** On a workspace that was already applied, a
setting set to `null` (or `serverless_policy.enabled: false`) is removed from Terraform's
state before apply (`scripts/tf.sh`), so the workspace keeps its current value. It is
never destroyed, because destroying a setting resets it: the provider erases a workspace
configuration key that leaves Terraform (`enableTokensConfig` would become `false`,
switching off every personal access token), and a deleted setting returns to the
platform default. `terraform/overrides.tf` maps each setting to what it owns.

**Governance is in the pull request, not the code.** Any default can be changed for one
workspace. What keeps that safe:
- **Plan guard** (`scripts/plan-guard.py`) lists, in the plan comment under **Before merging**,
  each change of a plan that (it never blocks):
  - deletes or replaces something people depend on (warehouses, cluster policies, usage
    policies, permissions, grants, entitlements, catalogs);
  - takes access away in an update (an entitlement, a catalog privilege, a permission), or
    makes the Starter warehouse admins only;
  - weakens security: a setting turned off, deleted or loosened, a catalog opened to every
    workspace, a grant to everyone, more token creators, dashboard embedding widened;
  - sets or changes the default catalog;
  - is one-way: the compliance security profile, or disabling legacy access (not flagged on
    a workspace where preflight found nothing that uses it).
- **The AI review** in the plan comment lists every deviation from the baseline, old and
  new value, security-relevant ones first.
- **Code owners** decide who approves which files.

## 4. Access model

**Groups.** One account group per role, named from a pattern in
`config/defaults/access.yaml` (a workspace can rename one):

| Persona (its group) | Entitlement | Default warehouse | Usage policy | Classic cluster policies | Catalog |
|---|---|---|---|---|---|
| users (`groups.users`): everyone | Consumer (Databricks One) | | | | |
| explorer (`groups.explorer`) | SQL access | Can use | User | By request | USE CATALOG, USE SCHEMA |
| builder (`groups.builder`) | Workspace and SQL access | Can use | User | By request | same |
| publisher (`groups.publisher`) | Workspace and SQL access | Can use | User | By request | same |
| platform admins (`{prefix}_platform_admins`) | Workspace admin | Manage | User, manager | Yes (workspace admins) | All privileges, MANAGE (the pipeline owns it) |

- Entitlements are tiers, each including the one before: Consumer access (Databricks One
  only) < SQL access (plus the SQL editor, queries, dashboards and Genie) < workspace
  access (the full workspace). A group gets the highest tier any of its personas has;
  the provider accepts Consumer access only on its own, so the module sets it only then.
- **Serverless first.** Every persona gets one serverless usage policy. Classic compute is
  the exception: three cluster policies per workspace (interactive, jobs, pipelines), one
  cluster per person each, whose users are granted on request (by a platform admin; a
  self-service app request is planned). Terraform does not manage who may use them, so those
  grants stay. Each person's clusters take IP
  addresses from the workspace's subnets; policies cap clusters per person, not per
  workspace, so the number of people approved is what bounds the total.
- Nobody gets "Allow unrestricted cluster creation". No persona is workspace admin:
  persona groups join the workspace as users; only the platform admins group as admin.
- Builder and publisher are the same here; what makes a publisher different is handled
  outside this project.
- The groups must be **account groups** (Entra ID groups synced to the account). Unity
  Catalog and usage policies cannot use groups that exist only in a workspace
  ([docs](https://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/workspace-local-groups)).
- Each workspace names its own persona groups (`groups:` in its file); only
  `{prefix}_platform_admins` comes from the baseline. A persona without a group is skipped.

**Sharing groups.** A workspace folder can be shared only with a group assigned to the
workspace. `sharing_groups` (in a workspace's file) assigns other Entra groups there **with
every entitlement off**, so people can share with them:

- **What someone can do** (sign in, SQL, notebooks) still comes only from their persona. A
  member with no persona can't sign in; one with a persona opens what is shared with the group.
- **Who sees what** follows the group's membership in Entra, with no change here.
- **Two guards** (`terraform/checks.tf`): a sharing group is never a persona, platform admins or
  users group, and sharing groups need the built-in `users` group without entitlements
  (`settings.users_group_entitlements`), which every assigned group's members get.
- Schemas don't need it: Unity Catalog grants take account groups directly.

**Requests.** Three paths, by volume and risk:

| Request | Path |
|---|---|
| A persona (explorer, builder, publisher) | The person asks in Entra (for example an access package), which adds them to the group. No pull request |
| A schema | The self-service app's jobs (section 9). Workspace folders: coming |
| A team warehouse, a project usage policy, classic compute | The self-service app, not built yet |

## 5. The workspace catalog

Each workspace gets one catalog, `{prefix}_citizen_dev` (`config/defaults/catalog.yaml`),
bound to the workspace, with predictive optimization on. Its schemas are not
Terraform's: people get them from the self-service app.

- **The pipeline owns the catalog.** It creates it, and every apply changes the catalog and
  its grants, which needs the owner (or a metastore admin). Handing ownership to a group the
  pipeline is not in would make the next apply fail. Platform admins get all privileges
  and `MANAGE` instead, which lets them grant, rename and drop. Being owner of its own
  catalog is all the pipeline needs; it is never metastore admin.
- **Catalog-level grants are minimal.** Personas get `USE CATALOG` and `USE SCHEMA`:
  enough to reach a schema and use what was shared with them, never data catalog-wide,
  and no `CREATE SCHEMA`. Data access is per schema.
- The grants are authoritative: anything else granted on the catalog by hand is removed
  on the next apply. A principal that needs a catalog privilege, such as the self-service
  app's service principal, is listed under `other_privileges`.

## 6. Caveats

1. **Disabling legacy access can become permanent** after 30 days (DBFS root and mounts,
   and user isolation, stay reversible). Before applying to an existing workspace, check
   nothing uses Hive tables, DBFS mounts or No-isolation clusters; until then set
   `disable_legacy_access`, `disable_dbfs_root_and_mounts` and `enforce_user_isolation` to
   `null` under `settings:` in its file.
2. **Terraform owns what it manages.** Entitlements, permissions, grants and budget
   policy access are authoritative: changes made by hand are reverted on the next apply
   (the drift check reports them first).
3. **Usage policies tag usage; they do not cap spend.** A user with several policies who
   does not choose gets the first alphabetically, so the workspace's policy is named
   `{PREFIX}-0-SELF-SERVICE`: project policies from the app apply only when picked. Policies
   need an account-level permission for the CI identity; without it, set
   `serverless_policy.enabled: false`.
4. **The SQL statement timeout** manages the workspace-wide SQL configuration as a whole.
5. **Enforce Unity Gateway** switches off the `databricks-` pay-per-token endpoints;
   model calls must use `system.ai` model services.
6. **`/Workspace/Shared` is open to all:** it grants `users` Can manage. Data access is
   still decided by Unity Catalog.
7. **Provider workaround:** `effective_workspace_label` is set to the label too (provider
   1.137.0 declares it optional instead of computed, which failed the apply).

## 7. Open questions

| # | Question | Default until decided |
|---|---|---|
| A1 | Restrict serverless egress (account network policy)? | Not managed |
| A2 | Private endpoints from serverless to the organization's storage? | Not managed |
| A3 | Budget alerts per business unit (account-level)? | Not managed |
| A4 | Audit log delivery to the SIEM? | Not managed |
| A5 | Personal Compute account setting: Delegate? (With On, every user can create personal clusters outside the classic cluster policies) | Not managed |
| S1 | Compliance security profile (one-way) or enhanced security monitoring? | Neither |
| S2 | Automatic cluster updates, and the window? | Not managed |
| S3 | Verbose audit logs (only useful with A4)? | Not managed |
| S4 | Interactive notebook results in the workspace's own storage? | Not managed |
| P5 | Approved dashboard embedding domains? | None |
| P7 | Narrow the Git allowlist to your GitHub organization (or add a GitHub Enterprise host)? | `https://github.com/`: every github.com repository |
| P8 | The chargeback tag set (it will change; one list in `config/defaults/cost.yaml`)? | `BUSINESS_UNIT`, `APPID`, `COST_CATEGORY`; users fill in `APPID`, `TEAM`, `PROJECT` on classic |
| P12 | Remove `users` from `/Workspace/Shared` so folder permissions mean something? | Organization only |

## 8. Not built yet

Ideas that are not built. Each needs review and a decision before work starts; the configuration is designed so they can be added without changing how workspaces are configured today.

| # | Addition | What it adds | Depends on |
| - | --- | --- | --- |
| F1 | Combined mode | Creating the workspace itself | Network design (VNet, PrivateLink, DNS) |
| F2 | Unity Catalog stream | Catalogs shared between workspaces, storage credentials, external locations | The Unity Catalog team |

### Combined mode (F1)

A second stack creates the workspace itself (Premium, VNet injection into an existing VNet, no public IP, front-end and back-end PrivateLink, private DNS) and passes the workspace URL to this stack. The workspace file would gain a `create: true` option and network settings; the onboarding steps stay the same.

### Unity Catalog stream (F2)

Catalogs shared between workspaces, storage credentials and external locations stay with the Unity Catalog team. This project manages only a workspace's own catalog (`config/defaults/catalog.yaml`) and expects the metastore and the rest to exist.

## 9. The self-service app

What people request (personal, project and team schemas; workspace folders are coming) comes
from the self-service app, an approvals app for the requests that need a person, and a schema job
for each workspace the app serves, all in the hub: Unity Catalog is shared across the metastore,
so **the app never calls another workspace** and needs no cross-workspace access. They live in this repository (`apps/self-service/`, `bundle/`,
`config/self-service/`) but are **not Terraform**: Databricks Asset Bundles deploy them
(`scripts/app_deploy.py`), because Terraform cannot deploy an app's code or start it, and the
app changes far more often than the baseline.

| Where | What | Deployed by |
| --- | --- | --- |
| **The hub** (`config/self-service/hub.yaml`) | Both apps, their Lakebase database, and each served workspace's schema job | `bundle/hub/`, `bundle/jobs/` |
| **Each served workspace** (a workspace file without `self_service: false`) | The baseline; its catalog and usage policy are bound to the hub too | Terraform |

**Every object has one owner.** Terraform's grants on catalogs, warehouses, usage policies and
entitlements are authoritative, so anything the bundles granted there would be removed by the
next apply. What the app needs on those, Terraform grants (`terraform/self_service.tf`):

| Object | Owner | The other never |
| --- | --- | --- |
| Workspace settings, persona groups, entitlements, workspace assignment | Terraform | the bundles touch none |
| The catalog `{prefix}_citizen_dev` and its grants, including the apps' `USE_CATALOG` and `BROWSE` | Terraform | the bundles and the jobs never grant on the catalog |
| Schemas in the catalog and their grants | The jobs, on request | Terraform never manages them |
| The catalog's and the usage policy's binding to the hub | Terraform (`terraform/self_service.tf`, `main.tf`) | the bundles never bind |
| The usage policy and who may use it (including the jobs' identity) | Terraform | the bundles only refer to its ID |
| The jobs, their notebooks and who may run them (the hub's two apps) | `bundle/jobs/` | Terraform never manages them |
| Both apps, their permissions, the Lakebase project, its database and migrations | `bundle/hub/`, `app_deploy.py` | Terraform never manages them |

**Configuration flows one way.** The app reads each served workspace's file and its Terraform
output `self_service` (prefix, ID, host, catalog, usage policy, platform admins), and never repeats them. One
value flows back: the apps' service principals (`app_ids` in `hub.yaml`), set once after the
hub's first deploy, which Terraform reads to grant them. Terraform loads nothing else from
`config/self-service/`, so an app setting never plans Terraform.

**A workspace's business unit is its prefix.** People are routed to their business unit's
workspace by a lookup function (`bu_lookup`) when one exists; until then, each person chooses
theirs once in the app (remembered, shown in the header, changeable), and their requests go
there. The jobs check every request
again; they run as the pipeline's identity on the workspace's usage policy.

**Deploys never overlap.** Terraform's state is per workspace in Azure Storage; the bundles'
state is in the workspaces (`<admin_path>/bundle/hub`, `<admin_path>/bundle/jobs`). The hub
deploys first (its apps must exist before the jobs can grant them), then each served
workspace's jobs.
