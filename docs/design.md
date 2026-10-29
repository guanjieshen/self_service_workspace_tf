# Citizen Development Workspace Baseline: Design

Why the project works the way it does. How to set it up is [SETUP.md](SETUP.md); how to
change the configuration is [config/README.md](../config/README.md); the workflows are
[github-actions.md](github-actions.md).

## 1. Purpose

Every citizen development workspace gets the same governed baseline: secure admin
settings, three personas with fixed rights, compute people can use straight away, one
Unity Catalog catalog, and chargeback tags. The
platform team runs it from Git: YAML only, reviewed in pull requests, applied by CI.

**In scope:** the configuration of an existing workspace (settings, personas, compute,
the workspace catalog, budget policies, Genie Code).
**Out of scope:** creating workspaces and networking (combined mode, future), the
metastore and shared catalogs, who is in which group (Entra ID), and everything people
request: schemas, workspace folders (the self-service app).

## 2. How it works

```
 Entra ID groups (synced to the account)          config/  (YAML, reviewed in pull requests)
 one group per persona, per workspace              defaults/          one baseline for every workspace
        │   membership: Entra                        workspaces/        one file per workspace
        │                                                 │
        ▼                                                 ▼
 ┌─────────────────────────── Terraform, one state per workspace ───────────────────────────┐
 │ settings │ entitlements │ warehouse, cluster, policies │ catalog + grants │ budget policies │
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
exist only in a workspace's file: `bu`, `host`, `tags`, `teams`, `team_warehouses`, `genie_code_instructions`.
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

| Persona (its group) | Entitlement | Default warehouse | Shared cluster | Cluster policy | Usage policy | Catalog |
|---|---|---|---|---|---|---|
| users (`groups.users`): everyone | Consumer (Databricks One) | | | | | |
| explorer (`groups.explorer`) | SQL access | Can use | | | User | USE CATALOG, USE SCHEMA |
| builder (`groups.builder`) | Workspace and SQL access | Can use | Can attach to | One cluster per person | User | same |
| publisher (`groups.publisher`) | Workspace and SQL access | Can use | Can attach to | One cluster per person | User | same |
| platform admins (`{bu}_platform_admins`) | Workspace admin | Manage | Manage | Manage | Manager | Owner; all privileges |

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
- Each workspace names its own persona groups (`groups:` in its file); only
  `{bu}_platform_admins` comes from the baseline. A persona without a group is skipped.

**Requests.** Three paths, by volume and risk:

| Request | Path |
|---|---|
| A persona (explorer, builder, publisher) | The person asks in Entra (for example an access package), which adds them to the group. No pull request |
| A schema or a workspace folder | The self-service app, outside this repository |
| A team warehouse | A person edits the workspace's file and opens a pull request: plan, AI review, approval, apply |

## 5. The workspace catalog

Each workspace gets one catalog, `{bu}_citizen_dev` (`config/defaults/catalog.yaml`),
bound to the workspace and owned by the platform admins group, with predictive
optimization and data classification on. Its schemas are not Terraform's: people get
them from the self-service app.

- **Catalog-level grants are minimal.** Personas get `USE CATALOG` and `USE SCHEMA`:
  enough to reach a schema and use what was shared with them, never data catalog-wide,
  and no `CREATE SCHEMA`. Data access is per schema. Platform admins get all privileges.
- The grants are authoritative: anything else granted on the catalog by hand is removed
  on the next apply, so the self-service app works with schemas, not catalog grants.

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
6. **`/Workspace/Shared` is open to all:** it grants `users` Can manage. Data access is
   still decided by Unity Catalog.
7. **Data classification needs a usage policy.** It runs on serverless; the identity
   running Terraform must be able to use a serverless usage policy, or turning it on fails
   with "Usage policy ID must not be empty". Workspaces without usage policies set
   `catalog.data_classification: null`.
8. **Provider workaround:** `effective_workspace_label` is set to the label too (provider
   1.137.0 declares it optional instead of computed, which failed the apply).

## 7. Open questions

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
| P8 | Required tag keys, and which a workspace sets for everything in it (`tags:`)? | Placeholders: `LOB`, `DEPARTMENT`, `TEAM` |
| P12 | Remove `users` from `/Workspace/Shared` so folder permissions mean something? | Organisation only |

## 8. Not built yet

Ideas that are not built. Each needs review and a decision before work starts; the configuration is designed so they can be added without changing how workspaces are configured today.

| # | Addition | What it adds | Depends on |
| - | --- | --- | --- |
| F1 | Combined mode | Creating the workspace itself | Network design (VNet, PrivateLink, DNS) |
| F2 | Unity Catalog stream | Catalogs shared between workspaces, storage credentials, external locations | The Unity Catalog team |
| F3 | The self-service app | Schemas and workspace folders on request | Its own repository; the catalog this repository creates |

### Combined mode (F1)

A second stack creates the workspace itself (Premium, VNet injection into an existing VNet, no public IP, front-end and back-end PrivateLink, private DNS) and passes the workspace URL to this stack. The workspace file would gain a `create: true` option and network settings; the onboarding steps stay the same.

### Unity Catalog stream (F2)

Catalogs shared between workspaces, storage credentials and external locations stay with the Unity Catalog team. This project manages only a workspace's own catalog (`catalog.yaml`) and expects the metastore and the rest to exist.

### The self-service app (F3)

Schemas and workspace folders are requested through the self-service app, which lives in its own repository and deploys its own jobs. What it relies on here:

- **The workspace catalog** (`{bu}_citizen_dev`), owned by the platform admins group. Personas have only `USE CATALOG` and `USE SCHEMA` on it; the app grants on the schemas it creates.
- **Catalog grants are authoritative:** a privilege granted on the catalog outside `catalog.yaml` is removed on the next apply. The app's service principal needs a privilege on the catalog (for example `CREATE SCHEMA`): add it to `catalog.yaml`, not by hand.
- **The persona groups** each workspace names in its file.
