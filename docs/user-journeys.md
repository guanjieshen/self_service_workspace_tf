# User journeys

The everyday changes, step by step, with what you see at each point. Each is one pull
request; nothing reaches a workspace until it is merged. The one-time setup is in
[SETUP.md](SETUP.md); every key you can set is in [config/README.md](../config/README.md).

| You want to | Files you touch | Workspaces deployed |
| --- | --- | --- |
| [1. Add a workspace](#1-add-a-workspace) | One new file | That one |
| [2. Change one workspace](#2-change-one-workspace) | Its file | That one |
| [3. Change every workspace](#3-change-every-workspace) | One file in `config/defaults/` | All of them |
| [4. Give someone access](#4-give-someone-access) | None (Entra ID) | None |
| [5. Retire a workspace](#5-retire-a-workspace) | Delete its file | None (its state is removed) |

## 1. Add a workspace

**Before you start** (outside the repository, done once per workspace):

- The workspace exists, and the pipeline's runners can reach it (its private endpoint and DNS).
- The pipeline's service principal is workspace admin there, and may create the catalog in its metastore (`CREATE CATALOG`, and `CREATE MANAGED STORAGE` on the external location if the catalog has its own storage) ([SETUP.md](SETUP.md), step 6, items 2 and 5).
- Its persona groups exist in Entra ID and are synced to the Databricks account ([SETUP.md](SETUP.md), step 7).
- A brand-new workspace: a workspace admin creates one personal access token and revokes it straight away, so the workspace has token permissions for Terraform to set ([SETUP.md](SETUP.md), step 9).

**In the repository:**

1. **Create the workspace's file.** Copy `config/workspaces/_example.yaml` to
   `config/workspaces/hr-citizen-dev.yaml` (in the GitHub web editor: Add file, then paste)
   and fill in:

   ```yaml
   prefix: hr
   host: https://adb-6543210987654321.3.azuredatabricks.net
   groups:
     users: hr-cd-users
     explorer: hr-cd-explorers
     builder: hr-cd-builders
     publisher: null          # nobody gets this persona here
   ```

   The file name (`hr-citizen-dev`) is the workspace's name in this repository.
2. **Open a pull request.**

**What happens:**

- The deploy workflow plans only `hr-citizen-dev`, because it is the only workspace file that changed.
- A comment titled **Plan: `hr-citizen-dev`** lists everything the first apply creates: the
  settings, the groups' access, the warehouse, the catalog, the policies.
- If something outside the repository is missing (a group not in the account, the service
  principal not an admin, no storage for the catalog), the comment says so at the top.
- The first plan is **flagged by the plan guard** (it sets the default catalog and makes the
  Starter warehouse admins only), so its check is red. A platform team member who has read the
  comment adds the `allow-risky-changes` label, and the check passes.
- **Merge when every check is green**, and the workspace is deployed. From the next Monday it
  is in the drift check.

## 2. Change one workspace

*For example: HR is not ready to switch off legacy access.*

1. Edit `config/workspaces/hr-citizen-dev.yaml`, and say why in a comment:

   ```yaml
   settings:
     disable_legacy_access: null     # still uses Hive tables; migrating by Q3
   ```

2. Open a pull request. Only `hr-citizen-dev` is planned; its comment shows the one change.
3. Merge. Only `hr-citizen-dev` is deployed.

Any baseline key can be set this way, with the same name and shape as in `config/defaults/`;
`null` leaves a setting alone.

## 3. Change every workspace

*For example: personal access tokens last at most 30 days everywhere.*

1. Edit `config/defaults/settings.yaml`: under `settings:`, set
   `personal_access_tokens.max_lifetime_days: 30`.
2. Open a pull request. Every workspace is planned, each in its own job, with a comment for
   each one it changes.
3. Merge. Every workspace is deployed, each in its own job; one that fails does not stop the
   others.

A workspace whose file sets its own value keeps it. A change that weakens security (a
setting turned off or loosened) fails the plan check until a person adds the label
`allow-risky-changes`.

## 4. Give someone access

*For example: Sam needs builder access in HR.*

Nothing in the repository: add Sam to `hr-cd-builders` in Entra ID. The repository says which
group holds each persona; who is in the group is Entra ID's business.

## 5. Retire a workspace

1. Delete `config/workspaces/hr-citizen-dev.yaml` and open a pull request. Nothing is planned: a **Retire** comment on the pull request says what merging does.
2. Merge. The workspace's Terraform state is removed, so Terraform no longer manages it.
   **Nothing in the workspace changes:** its settings, groups and data stay as they are.
   Deleting the workspace itself is a separate decision, outside this repository.
