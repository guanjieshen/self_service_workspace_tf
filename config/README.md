# Configuration

Everything your organization edits is in this folder (plus `.github/CODEOWNERS`). An upgrade of the framework never changes these files (README.md, "Installing and upgrading"); the exceptions are this README, `backend.hcl.example` and `workspaces/_example/`, which come with the framework.

**People are not in this folder.** Everything is granted to groups (`{bu}_explorer`, ...); who is in a group is managed in Entra ID, for example through access packages or a ticketing system. Giving someone a persona never needs a change here.

```
config/
├── defaults/                 the baseline: what every workspace gets
│   ├── access.yaml           the groups, the personas and what each gets, folders
│   ├── compute.yaml          SQL warehouses, shared cluster, the cluster policy
│   ├── cost.yaml             chargeback tags, usage (budget) policies
│   ├── catalog.yaml          the workspace catalog, shared schemas, personal schemas
│   ├── settings.yaml         admin console settings (security, downloads, tokens, Genie Code, ...)
│   └── genie-code/           default Genie Code instructions and skills
├── workspaces/<name>/        one folder per workspace
│   ├── workspace.yaml        which workspace (set once)
│   ├── access.yaml           teams                    + changes to defaults/access.yaml
│   ├── compute.yaml          team warehouses          + changes to defaults/compute.yaml
│   ├── cost.yaml, catalog.yaml, settings.yaml   (optional) changes to the defaults file of the same name
│   ├── genie-code/           (optional) this workspace's Genie Code instructions and skills
│   └── ai-review.yaml        (optional) the AI review's model for this workspace
├── ai-review.yaml            the AI review in the plan comment, for every workspace
└── backend.hcl               where Terraform state is kept
```

## The rule: same file, same keys

**A workspace changes a default by setting the same key, in the file with the same name.** Any key in `defaults/<file>.yaml` can be set in `workspaces/<name>/<file>.yaml`, with the same name and shape, and the workspace's value wins for that workspace:

```yaml
# defaults/settings.yaml                 # workspaces/fin-dev/settings.yaml
settings:                                settings:
  data_handling:                           data_handling:
    results_download: true                   results_download: false   # this workspace only
    notebook_export: true
```

- **Maps merge key by key.** Above, `fin-dev` turns off results download and keeps the baseline `notebook_export: true`.
- **A list or a single value replaces the default.**
- **`null` means Terraform leaves the setting alone.** The workspace keeps its current value. If Terraform managed the setting before, it stops managing it without changing it (`tf.sh` removes it from the state, a "release"): it is never reset.
- **A key the baseline does not have fails the plan**, with its name, so a typo cannot silently do nothing.
- **A key a workspace does not set keeps the baseline value**, so a change in `defaults/` reaches every workspace that has not changed that key.

A few keys exist only in a workspace's files, because they say who and what is in that workspace:

| File | Workspace-only keys |
| --- | --- |
| `workspace.yaml` | `bu`, `lob`, `account_id`, `host` (the workspace ID is read from it), `ci`, `label`, `auth` |
| `access.yaml` | `teams` (each with a group and tags: a folder, a usage policy) |
| `compute.yaml` | `team_warehouses` (each defined in full; the key must be a team in `access.yaml`) |

Start a new workspace from [`workspaces/_example/`](workspaces/_example/) with `scripts/workspaces.py new`. A missing file, or one with only comments, means the baseline.

## Common tasks

| Task | Every workspace | One workspace |
| --- | --- | --- |
| Give someone a persona | | Add them to the group in Entra ID (`{bu}_explorer`, ...); no change here |
| Use differently named groups | `groups` in `defaults/access.yaml` | `groups.<persona>` in its `access.yaml` |
| Change what a persona can do | `personas` in `defaults/access.yaml` | `personas.<persona>.<key>` in its `access.yaml` |
| Let another persona create tokens | `personas.<persona>.can_create_tokens` in `defaults/access.yaml` | the same key in its `access.yaml` |
| Add a team (its tags allowed on cluster policies) | | `teams` in its `access.yaml` |
| Create a workspace folder | | Run the `<BU> team folder` job with `folder`, `requested_by` and, optionally, `owner_group`, `reason` and `request_id` (a ticket reference) |
| Create a personal schema | | Run the `<BU> personal schema` job with `user` and `catalog` |
| Let a service principal run the jobs (a ticketing system, an app) | `jobs.runners` in `defaults/access.yaml` | the same key in its `access.yaml` (its application ID) |
| Give a team its own warehouse | | `team_warehouses` in its `compute.yaml` |
| Add a shared schema (with grants) | | `catalog.schemas` in its `catalog.yaml` |
| Change personal schemas (prefix, privileges) | `personal_schemas` in `defaults/catalog.yaml` | the same key in its `catalog.yaml` |
| Resize the default warehouse | `sql_warehouse` in `defaults/compute.yaml` | `sql_warehouse.size` (etc.) in its `compute.yaml` |
| Change an admin setting | `settings.<key>` in `defaults/settings.yaml` | the same key in its `settings.yaml` |
| Not ready to switch off legacy access and DBFS | | `settings.disable_legacy_access: null` and `disable_dbfs_root_and_mounts: null` in its `settings.yaml` |
| Leave a setting alone (something else manages it) | the key set to `null` in `defaults/` | the key set to `null` in its file |
| Leave group assignment, token permissions or catalog grants alone | `manage` in `defaults/access.yaml` | `manage.<key>: false` in its `access.yaml` |
| Leave budget policies alone | `budget_policies.enabled: false` in `defaults/cost.yaml` | the same in its `cost.yaml` |
| Change Genie Code instructions | `defaults/genie-code/instructions.md` | its `genie-code/instructions.md` (appended after the default) |
| Add a Genie Code skill | a folder in `defaults/genie-code/skills/` | a folder in its `genie-code/skills/` |
| Leave Genie Code alone (managed elsewhere) | `settings.genie_code` in `defaults/settings.yaml` | `settings.genie_code: null` in its `settings.yaml` |
| Show a label next to the workspace name | | `label` in its `workspace.yaml` |

After an edit: open a pull request. Its plan comment shows what changes in each workspace. Locally: `./scripts/tf.sh <name> plan`, or `./scripts/tf.sh all plan` after changing `defaults/`.

## How changes are reviewed

Any default can be changed for one workspace, so differences from the baseline are caught in the pull request rather than forbidden by the code:

- **Plan guard** (`scripts/tf.sh`, and the plan check on every pull request) fails the check when a plan deletes or replaces something people depend on (folders, warehouses, clusters, policies, budget policies, permissions, grants, catalogs), or weakens security: a security setting turned off, deleted or loosened, a catalog opened to every workspace, a grant to everyone, more groups allowed to create tokens. A person must add the label `allow-risky-changes`.
- **The AI review** in the plan comment calls out every workspace file that changes a baseline value, with the old and new value, and flags security-relevant ones first.
- **Code owners** (`.github/CODEOWNERS`) decide who must approve which files: the platform team for `defaults/` and everything outside `config/`, security for `defaults/settings.yaml`.

Put the reason for a difference in a comment next to it: the reviewer sees it in the diff.

## Conventions in the baseline files

| You see | It means |
| --- | --- |
| `null` | Terraform leaves the setting alone. |
| `{BU}` / `{bu}` | The workspace's business unit code, upper / lower case. |
| `{KEY}` | A team or project key, upper case. |
| `{PERSONA}` | A persona name, such as Builder. |
| `CAN_USE`, `CAN_RESTART`, ... | Databricks permission levels, as shown in the workspace UI. |
| `ONE-WAY` in a comment | Cannot be undone once applied. |
| "Decide at onboarding" | Switching it later on a busy workspace is disruptive; decide it before the first apply. |
