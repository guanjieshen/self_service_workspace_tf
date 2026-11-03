---
name: change-one-workspace
description: Use when someone wants to change the custom configuration of one managed workspace only: its groups (which Entra group holds an access level), its warehouse size, its tags or APPID, a label, groups people may share folders with, an admin setting for that workspace, Genie Code instructions for it, leaving the self-service app out, or to stop managing (retire) it. Edits config/workspaces/<name>.yaml and hands over to pull-request-from-databricks.
---

# Change one workspace's configuration

The person may not know YAML or Terraform. Ask which workspace (the file name in `config/workspaces/`, or its address: match it to a file's `host`), then what they want in their own words; at most two questions at a time. If they mean every workspace, use the skill **change-all-workspaces** instead.

## 1. Find the key

1. Look the request up in `config/README.md`, **Common tasks**, column "One workspace".
2. Read the same key in `config/defaults/` and its comment (what it does, its values). In the workspace's file it has **the same name and shape**.
3. If nothing fits, say so: who is in a group is Entra ID (no change here), and changing the framework's code is for its maintainers.

Common ones, in `config/workspaces/<name>.yaml`:

| They want to... | Key |
| --- | --- |
| Use another Entra group for an access level | `groups.<persona>` (users, explorer, builder, publisher; `null` = nobody) |
| A bigger or smaller default warehouse here | `sql_warehouse.size` |
| Set this workspace's APPID, or another tag value | `tags.APPID`; `tags.<KEY>: null` drops a tag here |
| Let people share folders with an Entra group (it gets no access by itself) | `sharing_groups: [<group>]` (not a persona, admins or users group) |
| A label next to the workspace's name | `label: {text: DEV, color: lime}` (coral, lemon, lime, turquoise, indigo, purple, pink) |
| An admin setting differs here | `settings.<key>` (`null` = leave it alone here) |
| Genie Code knows about this workspace | `genie_code_instructions: |` then Markdown (added after the baseline's) |
| Leave the self-service app out of it | `self_service: false` |
| Stop managing it | delete the file: Terraform forgets it, **nothing in the workspace changes** |

## 2. How a workspace file overrides the defaults

- A **map** merges key by key: `sql_warehouse: {size: Large}` changes only the size.
- Anything else (a value, a list) **replaces** the default.
- **`null`** means "this project leaves it alone here" (it does not reset it).
- Add a comment saying **why** this workspace differs: every difference is reviewed.

## 3. Be careful with

- **`prefix` and `host`:** never change them (the prefix names everything created there; changing it recreates them). Stop and say a maintainer should plan it.
- **Security and access:** turning a protection off, or removing a group's access, is listed under **Before merging**: say plainly what it opens or removes.
- **Values you do not have:** never guess a group name or a URL.

## 4. Edit, read back, deploy

1. Change only what was asked, with a comment; two spaces per level, no tabs.
2. Read it back ("in hr only, builders are now hr-data-builders").
3. Hand over to the skill **pull-request-from-databricks**. Only this workspace is planned (**Plan `<name>`**): go through its plan comment with them. Retiring shows a comment saying what merging retires.
