<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/my-projects/. Lists what someone
made in this workspace, and removes a project cleanly.
-->
---
name: my-projects
description: Use when someone asks what they have built or own in this workspace, what is still running or costing money, which of their apps are left on, or wants to clean up, remove or retire a project, an app, a pipeline, a job, a dashboard, a Genie space or a schema.
---

# My projects: what I made, and cleaning up

## 1. What they made

Find what they created (as them; show only theirs) and group it by project (the `<prefix>-<kind>-<name>` names, and each project's `AGENTS.md` under `/Workspace/Users/<their email>/projects/`):

| Kind | Look for | Show |
| --- | --- | --- |
| **Apps** | Apps they created | Its state (running or stopped), its `LEAVE_ON` tag, its URL |
| **Databases** | Lakebase projects tagged `OWNER` = them | Their tags; each pauses on its own when unused |
| **Pipelines and jobs** | Those they created | When they last ran, and their schedule |
| **Dashboards and Genie spaces** | Those they own | Who they're shared with |
| **Schemas** | Their temporary and permanent schemas in `{CATALOG}` | A temporary schema's delete date (`cd_expires`) |

Say what is running all the time (an app with `LEAVE_ON` true), and what hasn't been used in a while.

## 2. Leave on, or turn off

Every app carries a `LEAVE_ON` tag: `false` means the platform team may turn it off when it isn't needed (a job will do it); `true` keeps it running, and costing money, all the time. Change it when they ask (for example when others rely on it every day), with the entity tags API (`POST /api/2.0/entity-tag-assignments`, `entity_type` `apps`), and say what it means for cost.

## 3. Remove a project

Only with their clear yes, part by part, showing what each removal deletes (what's removed is gone for good):

1. **Apps**, and each app's Lakebase database (a removed database keeps its name for 7 days).
2. **Jobs**, then **pipelines** (a pipeline's tables stay until their schema goes).
3. **Dashboards** and **Genie spaces**.
4. **Schemas:** a temporary one is deleted on its date anyway; a permanent one only on request through TIS.
5. The project's **folder**, last.

Then tell them what is left, if anything.
