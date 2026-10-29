# Configuration

Everything your organization edits is in this folder (plus `.github/CODEOWNERS`). An upgrade of the framework never changes these files ([docs/SETUP.md](../docs/SETUP.md), "Upgrade to a new release"); the exceptions are this README and `workspaces/_example.yaml`, which come with the framework.

**People are not in this folder.** Everything is granted to groups (each workspace names its own); who is in a group is managed in Entra ID, for example through access packages or a ticketing system. Giving someone a persona never needs a change here.

```
config/
├── defaults/                 the baseline: what every workspace gets
│   ├── access.yaml           the personas and what each gets; the platform admins group
│   ├── compute.yaml          the default SQL warehouse, the classic cluster policies
│   ├── cost.yaml             the account ID, chargeback tags, usage (budget) policies
│   ├── catalog.yaml          the workspace catalog and its grants
│   ├── settings.yaml         admin console settings (security, downloads, tokens, Genie Code, ...)
│   └── genie-code/           Genie Code instructions and skills, for every workspace
├── workspaces/               one file per workspace: the list of workspaces CI deploys
│   ├── _example.yaml         the template to copy
│   └── <name>.yaml           a workspace: bu, host, its groups, and any change to the baseline
├── setup.yaml                the setup values (docs/SETUP.md, step 1), and the AI review's workspace
└── backend.hcl               where Terraform state is kept (written by scripts/setup.py state)
```

## A workspace is one file

`workspaces/<name>.yaml` says who the workspace is and how it differs from the baseline. Copy [`workspaces/_example.yaml`](workspaces/_example.yaml) and fill it in:

```yaml
# workspaces/hr-citizen-dev.yaml
bu: hr                     # business unit code: used in names ({bu}_citizen_dev, <BU> Default Warehouse, ...)
host: https://adb-6543210987654321.3.azuredatabricks.net
groups:                    # the Entra ID group that holds each persona; null = nobody
  users: hr-cd-users
  explorer: hr-cd-explorers
  builder: hr-cd-builders
  publisher: null

settings:                  # a change to the baseline, for this workspace only
  disable_legacy_access: null   # not ready for Unity Catalog only yet
```

`<name>` (the file name) is the workspace's name in this repository: in its workflow jobs, its plan comment and its state file. Adding a file adds a workspace; deleting it stops managing that workspace (nothing in it changes).

## The rule: the same key as the baseline

**A workspace changes a default by setting the same top-level key, with the same shape.** Every key in `defaults/` is defined in exactly one of its files, so the workspace file does not need to know which:

```yaml
# defaults/settings.yaml                 # workspaces/fin-dev.yaml
settings:                                settings:
  data_handling:                           data_handling:
    results_download: true                   results_download: false   # this workspace only
    notebook_export: true
```

- **Maps merge key by key.** Above, `fin-dev` turns off results download and keeps the baseline `notebook_export: true`.
- **A list or a single value replaces the default.**
- **`null` means Terraform leaves the setting alone.** The workspace keeps its current value. If Terraform managed the setting before, it stops managing it without changing it (`tf.sh` removes it from the state, a "release"): it is never reset.
- **A key that is neither in the baseline nor a workspace key fails the plan**, with its name, so a typo cannot silently do nothing.
- **A key a workspace does not set keeps the baseline value**, so a change in `defaults/` reaches every workspace that has not changed that key.

The workspace keys (not in the baseline):

| Key | |
| --- | --- |
| `bu` | Required. The business unit code, used in every name |
| `host` | Required. The workspace URL; the workspace ID is read from it (or set `id`) |
| `groups` | The group for each persona (a baseline key: the platform admins group comes from the baseline) |
| `genie_code_instructions` | Genie Code instructions for this workspace (Markdown), after the baseline's |
| `label` | A label and color next to the workspace name in the top bar |
| `account_id`, `auth`, `id` | Rarely: another Databricks account than the baseline's; CLI profiles for local runs; the workspace ID when the host does not show it |

## Common tasks

| Task | Every workspace | One workspace |
| --- | --- | --- |
| Add a workspace | | Copy `workspaces/_example.yaml` to `workspaces/<name>.yaml` and fill in `bu`, `host`, `groups` |
| Stop managing a workspace | | Delete its file (its Terraform state goes; the workspace is unchanged) |
| Give someone a persona | | Add them to the workspace's group for it in Entra ID; no change here |
| Change which group holds a persona | | `groups.<persona>` in its file |
| Change what a persona can do | `personas` in `defaults/access.yaml` | `personas.<persona>.<key>` in its file |
| Let another persona create tokens | `personas.<persona>.can_create_tokens` in `defaults/access.yaml` | the same key in its file |
| Add, remove or rename a chargeback tag | `tags` (and `classic_user_tags`) in `defaults/cost.yaml` | `tags.<KEY>` in its file (`null` drops it) |
| Set a workspace's APP_ID (or another tag value) | | `tags.APP_ID` in its file |
| Change the classic cluster policies' limits | `cluster_policy` in `defaults/compute.yaml` (shared rules, then `interactive`, `jobs`, `pipelines`) | `cluster_policy.<key>` in its file; `cluster_policy.pipelines: null` to leave that policy alone (none on a new workspace) |
| A team warehouse, a project usage policy, access to classic compute | | The self-service app, not this repository |
| Resize the default warehouse | `sql_warehouse` in `defaults/compute.yaml` | `sql_warehouse.size` (etc.) in its file |
| Change an admin setting | `settings.<key>` in `defaults/settings.yaml` | the same key in its file |
| Not ready to switch off legacy access and DBFS | | `settings.disable_legacy_access`, `disable_dbfs_root_and_mounts` and `enforce_user_isolation`: `null` in its file |
| Leave a setting alone (something else manages it) | the key set to `null` in `defaults/` | the key set to `null` in its file |
| Leave the serverless usage policy alone | `serverless_policy.enabled: false` in `defaults/cost.yaml` | the same in its file |
| Change Genie Code instructions | `defaults/genie-code/instructions.md` | `genie_code_instructions` in its file (appended after the default) |
| Add a Genie Code skill | a folder in `defaults/genie-code/skills/` | (every workspace gets the baseline's skills) |
| Leave Genie Code alone (managed elsewhere) | `settings.genie_code` in `defaults/settings.yaml` | `settings.genie_code: null` in its file |
| Show a label next to the workspace name | | `label` in its file |

After an edit: open a pull request. Its plan comments show what changes in each workspace it concerns. Locally: `./scripts/tf.sh <name> plan`, or `./scripts/tf.sh all plan` after changing `defaults/`. More examples: [docs/user-journeys.md](../docs/user-journeys.md).

## How changes are reviewed

Any default can be changed for one workspace, so differences from the baseline are caught in the pull request rather than forbidden by the code:

- **Plan guard** (`scripts/tf.sh`, and the plan check on every pull request) fails the check when a plan deletes or replaces something people depend on (warehouses, clusters, policies, budget policies, permissions, grants, catalogs), or weakens security: a security setting turned off, deleted or loosened, a catalog opened to every workspace, a grant to everyone, more groups allowed to create tokens. A person must add the label `allow-risky-changes`.
- **The AI review** in the plan comment calls out every value in a workspace file that differs from the baseline, with the old and new value, and flags security-relevant ones first.
- **Code owners** (`.github/CODEOWNERS`) decide who must approve which files: the platform team for `defaults/` and everything outside `config/`, security for `defaults/settings.yaml`.

Put the reason for a difference in a comment next to it: the reviewer sees it in the diff.

## Conventions in the baseline files

| You see | It means |
| --- | --- |
| `null` | Terraform leaves the setting alone. |
| `{BU}` / `{bu}` | The workspace's business unit code, upper / lower case. |
| `{TAGS}`, `{WORKSPACE_TAGS}` (Genie Code text) | Every chargeback tag; the ones set for you, with their values. |
| `CAN_USE`, `CAN_RESTART`, ... | Databricks permission levels, as shown in the workspace UI. |
| `ONE-WAY` in a comment | Cannot be undone once applied. |
| "Decide at onboarding" | Switching it later on a busy workspace is disruptive; decide it before the first apply. |
