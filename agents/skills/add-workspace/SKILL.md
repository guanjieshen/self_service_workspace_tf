---
name: add-workspace
description: Use when someone wants to add (onboard) a Databricks workspace so this project manages it, bring a new business unit's workspace under the baseline, or "set up a new citizen development workspace". Asks for each value in plain language, checks what must be done outside the repository, writes config/workspaces/<name>.yaml, and hands over to pull-request-from-databricks.
---

# Add a workspace

The person may not know Terraform, YAML or git. Ask at most two questions at a time, in plain words, and explain why each value is needed. **Never invent a value** (a URL, a group name, a storage path): if they do not know it, say who usually does and stop until they have it.

Work in this repository's Git folder. The only file you create is `config/workspaces/<name>.yaml`, copied from `config/workspaces/_example.yaml` (read it first: its comments are the reference).

## 1. Before anything: what must already be done (outside the repository)

Ask them to confirm each one. If one is missing, say who does it and stop: the pull request's plan would fail on it.

| Needed | Who | How to check |
| --- | --- | --- |
| The workspace exists (Premium), and has a Unity Catalog metastore | Databricks account admin | It opens; Catalog shows catalogs |
| The pipeline's service principal is **workspace admin** in it | Databricks account admin | Settings > Identity and access > Service principals: it is listed, in `admins` |
| One **Entra ID group per access level** (users, explorer, builder), synced to the Databricks account | Identity team | Account console > User management > Groups: each group is there |
| A brand-new workspace: one personal access token **created and revoked** by a workspace admin, so token permissions exist | Workspace admin | Settings > Developer > Access tokens: create one, then revoke it straight away |

Also ask whether the workspace's catalog needs its own storage (the metastore has no storage root): then they need a storage path (`abfss://...`) that an external location covers. If unsure, leave it out: the plan says so if it is needed.

## 2. The values

| Ask | Key | Rules and example |
| --- | --- | --- |
| A short name for this workspace in the repository | the file name | lowercase letters, digits, dashes, underscores: `hr-citizen-dev` |
| The workspace's address | `host` | its per-workspace URL, `https://adb-<number>.<n>.azuredatabricks.net` (the browser's address bar when they open the workspace, up to `.net`) |
| A short prefix | `prefix` | short, lowercase letters and digits, unique across workspaces: `hr` (it becomes part of the catalog's name, which allows only those). It names everything created there (`hr_citizen_dev`, `HR Default Warehouse`) and is the business unit people choose in the self-service app. **It cannot be changed later** without recreating those |
| The group for everyone who may use it (dashboards, Genie, apps) | `groups.users` | the Entra group's exact name, or `null` |
| The group for SQL, dashboards and Genie | `groups.explorer` | exact name, or `null` (nobody gets it) |
| The group for the full workspace (notebooks, jobs, pipelines) | `groups.builder` | exact name, or `null` |
| The group for publishing (often nobody yet) | `groups.publisher` | exact name, or `null` |

Optional, only if they bring it up: `label` (a coloured tag next to the workspace name: text, and one of coral, lemon, lime, turquoise, indigo, purple, pink), `tags.APPID`, `catalog.storage_root`, `sql_warehouse.size` (2X-Small, X-Small, Small, Medium, Large, X-Large, ...; the baseline's is Medium), `sharing_groups`. For anything else, use the skill change-one-workspace after this.

Check before writing: the prefix and the host are not already used by another file in `config/workspaces/` (open them and look).

## 3. Write the file

Create `config/workspaces/<name>.yaml` with only what they gave, each value with a short comment saying what it is. For example:

```yaml
# The HR citizen development workspace (onboarded <date>).
prefix: hr
host: https://adb-6543210987654321.3.azuredatabricks.net

groups:
  users: hr-cd-users
  explorer: hr-cd-explorers
  builder: hr-cd-builders
  publisher: null          # nobody gets this persona here yet
```

Two spaces per level, no tabs. Read it back to them in plain words: "the hr workspace, at <host>, where hr-cd-explorers get SQL and dashboards...". Fix anything they correct.

## 4. Review and deploy

Hand over to the skill **pull-request-from-databricks**. On the pull request, tell them what to expect:

- Only this workspace is planned (**Plan `<name>`**). Its plan comment lists everything the first apply creates: settings, group access, the warehouse, the catalog, the usage policy.
- **Before merging** lists what is hard to undo on a first apply (the default catalog is set; the Starter Warehouse becomes admins only): confirm with them that it is intended.
- If the plan says something outside the repository is missing (a group not found, the identity not an admin), go back to step 1.

After the merge, the workspace is managed, and (if the self-service app is set up) its business unit appears in the app on the next deploy, with its two jobs.
