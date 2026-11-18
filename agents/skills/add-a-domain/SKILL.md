---
name: add-a-domain
description: Use when someone wants some groups in one workspace to have their own SQL warehouse, their own serverless usage policy, their own APPID or their own folder (a domain, for example finance or supply chain), or wants to change or remove such a domain. Edits domains in config/workspaces/<name>.yaml and hands over to pull-request-from-databricks.
---

# Add, change or remove a domain in a workspace

A **domain** is a set of Entra groups inside **one** workspace that get **their own SQL
warehouse, their own serverless usage policy and their own APPID**, and optionally **their own
folder**, on top of what the whole workspace has (which everyone keeps). Access itself still comes from the personas: a domain's
groups are listed by persona (explorer, builder, publisher) and get that persona's access.

The person may not know YAML or Terraform. Ask, at most two questions at a time, in their words.
If they want something for **every** user of the workspace, use the skill **change-one-workspace**
instead; for every workspace, **change-all-workspaces**.

## 1. Get what you need (never guess a value)

| Ask for | Becomes | Rules |
| --- | --- | --- |
| Which workspace | the file `config/workspaces/<name>.yaml` (match its `host` if they give an address) | It must exist; to add one, the skill **add-workspace** first |
| The domain's name | the key under `domains:`, for example `finance` or `supply_chain` | Lowercase letters, digits and `_`, starting with a letter. It names the warehouse and the policy, so **choose it once**: renaming replaces both |
| Its groups, for each access level | `groups.explorer`, `groups.builder`, `groups.publisher` | Entra groups that already exist **in the Databricks account** (the plan's preflight checks). One name or a list. A group is in **one** domain only, and not also under the workspace's own `groups:` |
| Its application ID | `tags.APPID` | **Required**, and not `NONE`. Ask for the exact ID: it is what costs are charged to |
| A warehouse size, only if they say | `sql_warehouse.size` | 2X-Small, X-Small, Small, Medium, Large, ... Otherwise the workspace's default size |
| Whether the domain needs its own folder | `folder: true` | `/Workspace/Domains/<Name>`. Only the domain's groups see it. For a folder for a team or a project, use the self-service app instead (a folder request): that is not a domain |

Optional, only if they bring it up: other tag values (`tags.<KEY>`; `null` drops the workspace's
tag for this domain), other warehouse keys (`auto_stop_minutes`, `min_clusters`, `max_clusters`,
`type`, `name`), or another policy name (`serverless_policy.name`, which must contain `{PREFIX}`).

## 2. Write it

In the workspace's file, two spaces per level, with a comment saying who asked and why:

```yaml
domains:
  finance:                              # Finance analytics (asked by <who>, <date>)
    groups:
      explorer: [edm-gds-finance-explorer]
      builder: edm-gds-finance-builder
    tags:
      APPID: APP-5678                   # the domain's own application ID
    sql_warehouse: {size: Small}        # only if they asked for a size
    folder: true                        # only if they want the domain's folder
```

Then read it back in plain words: "In gds, the finance domain: edm-gds-finance-explorer can use
SQL, dashboards and Genie, edm-gds-finance-builder the full workspace, both with their own
**GDS Finance Warehouse** and usage policy **GDS-0-DOMAIN-FINANCE**, charged to APP-5678."

## 3. What it does, so you can explain it

- **Access:** the domain's groups get their persona's access, like the workspace's own groups:
  sign-in, the catalog, the workspace's default warehouse and usage policy.
- **Its warehouse:** `{PREFIX} <Name> Warehouse`, which only its groups may use (the platform
  admins manage it), tagged with the domain's APPID and `DOMAIN`.
- **Its usage policy:** `{PREFIX}-0-DOMAIN-<NAME>`, for its groups (and the platform admins). It
  is the one their serverless usage goes to when they pick none, because it sorts before the
  workspace's. They can still pick the workspace's.
- **Its folder** (with `folder: true`): `/Workspace/Domains/<Name>`. Only the domain's groups
  get it: those under explorer may open it, those under builder or publisher manage it, and the
  platform admins manage it. The workspace's own groups do not get it. What people make inside
  it inherits that. Sharing the domain's folder itself by hand is undone at the next deploy:
  change the domain's groups instead.
- **Dashboards and Genie spaces** use the warehouse their builder chose: tell the domain's builders
  to choose the domain's warehouse, or its SQL usage is charged to the workspace's APPID.

## 4. Be careful with

- **Removing a domain, or renaming it,** deletes its warehouse and its usage policy (the plan
  lists them under **Before merging**). Dashboards and Genie spaces on that warehouse stop working
  until they are moved to another one. Say so plainly and get a yes first.
- **Removing its folder** (the domain, or `folder: true`) is refused by Databricks while the folder
  holds anything, so the deploy fails rather than deleting work: its contents must be moved first.
- **Removing a group from a domain** removes that group's access to the workspace, unless it is
  in another persona group too.
- **A group that does not exist in the account yet** fails the plan's preflight. If it exists in
  Entra but the plan cannot find it, add it once in the account console (User management >
  Groups > Add group), then run the plan again.

## 5. Deploy

Hand over to the skill **pull-request-from-databricks**. Only this workspace is planned: go through
its plan comment with them. Adding a domain shows only new resources: its groups' assignments,
entitlements and catalog grants, one usage policy, one warehouse with its permissions, and with
`folder: true` one folder with its permissions.
