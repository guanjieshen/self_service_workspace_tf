---
name: change-all-workspaces
description: Use when someone wants to change the default (baseline) for every managed workspace at once, such as the default warehouse size, chargeback tags, the usage policy, what an access level (persona) can do, who may create tokens, admin and security settings, cluster policy limits, or Genie Code's instructions and skills. Edits config/defaults/, warns which workspaces override the value, and hands over to pull-request-from-databricks.
---

# Change the defaults for every workspace

The person may not know YAML or Terraform. Ask what they want in their own words, then translate; at most two questions at a time.

**The defaults are `config/defaults/`**: one file per area (access, compute, cost, catalog, settings) and `config/defaults/genie-code/`. A change there reaches **every** workspace in `config/workspaces/`. If they mean only one workspace, use the skill **change-one-workspace** instead. For Genie Code's instructions, skills or business context, use the skill **change-genie-code**.

## 1. Find the key

1. Look the request up in `config/README.md`, **Common tasks**, column "Every workspace".
2. Open that file in `config/defaults/` and read the key's comment: **it is the key's documentation** (what it does, its values, what `null` means).
3. If nothing fits, search the comments in `config/defaults/*.yaml`. If it still does not fit, say so: some things are not managed here (creating workspaces, the metastore, who is in a group: that is Entra ID), and changing the framework's code is for its maintainers.

Common ones: the default warehouse, `sql_warehouse` in `config/defaults/compute.yaml`; tags, `tags` in `config/defaults/cost.yaml`; who may create tokens, `personas.<persona>.can_create_tokens` in `config/defaults/access.yaml`; an admin or security setting, `settings.<key>` in `config/defaults/settings.yaml`.

## 2. Check which workspaces will not follow

A workspace file may set the same key for itself, and then keeps its own value. Open each file in `config/workspaces/` (not `_example.yaml`) and list the ones that set the key. Tell them: "this changes every workspace except hr and finance, which set their own". Ask whether those should change too (then edit their files: the skill change-one-workspace).

## 3. Be careful with

- **Security and access settings:** turning a protection off, or removing access, is listed under **Before merging** on the pull request. Say plainly what it opens or removes, in every workspace, and that a reviewer must agree. `.github/CODEOWNERS` may require the security team for `config/defaults/settings.yaml`.
- **`null`** means "this project leaves the setting alone in every workspace" (it does not reset it).
- **Names** (`catalog.name`, the warehouse's `name`): changing them recreates resources everywhere. Do not; say a maintainer should plan it.

## 4. Edit, read back, deploy

1. Change only the key asked for, keep its comment up to date, two spaces per level, no tabs.
2. Read it back in plain words ("every workspace's default warehouse becomes Large, except hr").
3. Hand over to the skill **pull-request-from-databricks**. **Every workspace is planned:** go through each plan comment with them; they should all show the same change, and nothing else.
