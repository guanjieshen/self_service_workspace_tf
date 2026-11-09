---
name: update-self-service-app
description: Use when someone wants to change the self-service (Citizen Development) app or the approvals app, such as their links (FAQ, SOPs, persona requests, Discover), the guided tour's prompt, a banner, the header's name or colour, the title, which requests need an approver, the AI model (Validate, the approvers' summary, schema comments), who may open each app, the jobs' settings (schema prefix and rights, temporary schemas' days, where folders go), the daily temporary schema cleanup, set the app up for the first time (the hub), or add a business unit to it. Says whether it is a Settings change (no pull request) or a file change, makes the edit, and hands over to pull-request-from-databricks.
---

# Update the self-service app

The person may not know YAML or git. Ask what they want in their own words; at most two questions at a time. **First decide where the change goes**: many need no pull request.

## 1. Settings, no pull request (the approvals app)

These are changed by a platform admin in the **approvals app > Settings** and show in the self-service app within 15 seconds. Point them there; do not edit a file for these.

| They want to... | Settings tab |
| --- | --- |
| A banner across every page (planned maintenance, ...) | **Announcement** |
| The word at the start of both apps' header (Databricks by default), or its colour | **Branding** > Header |
| The guided tour's prompt (what Genie One is asked the first time someone opens their workspace; `{business_unit}` and `{catalog}` are filled in with theirs) | **Onboarding** > Guided tour |
| The links to request Explorer, Builder or Publisher access (for example ServiceNow items), for all business units or one | **Onboarding** > Persona request links, with its **Business unit** selector |
| FAQ links next to each section, or the standard operating procedure behind each task | **Help links** |
| How many temporary schemas each person may have at a time (1 by default, up to 10) | **Schemas** > Temporary schemas |
| The AI model every AI feature uses (Validate, the approvers' summary, new schemas' comments), or turn AI off (empty) | **AI** > AI model |
| See who changed what, and when | **Change history** |

## 2. A pull request: `config/self-service/app.yaml`

What people may do, and how the app behaves. Read the key's comment in the file before editing.

| They want to... | Key (under `self_service_app:` unless said) |
| --- | --- |
| Which requests wait for an approver | `human_approval` (from `project_schema`, `team_schema`, `temporary_schema`; the others are created straight away). Workspace folders always wait: an admin makes them by hand for now |
| The Validate check on forms (AI advice on the name and reason) | `ai_check`: `"on"` or `"off"` |
| Route people to their own business unit from a directory, instead of them choosing it once | `bu_lookup.function`: a SQL function, email in, business unit out (`catalog.schema.function`), run on `hub.warehouse_id` in `hub.yaml`. Its owner grants the self-service app EXECUTE, outside this repository. `null` = they choose |
| The default AI model, for every AI feature (Validate, the approvers' summary, new schemas' comments) | `ai_model` (`null` = no AI; admins change it in Settings > AI). An `app.yaml` from 1.0.x names it `ai_summary` (`model:` under it): still read; replacing it with `ai_model` is optional |
| A wiki link in the header, a short link to the app | `links.wiki`, `links.go_link` |
| The **Add a group to your workspace** card (otherwise Coming soon) | `links.group_request`: their request form's URL |
| The guided tour's default prompt (Settings > Onboarding overrides it; Reset comes back to it) | `onboarding.prompt` |
| The header's title (Settings > Branding changes only its first word) | `title` |
| The name prefix of every schema the app makes (`cd_`), or the rights of project and team schemas (and of a temporary schema kept as one) | `personal_schema.prefix`, `personal_schema.privileges` (under `jobs:`) |
| How long a temporary schema lasts (its `cd_expires` tag; the daily cleanup job drops it after) | `temporary_schema.days` (under `jobs:`, 1 to 365) |
| What a temporary schema's requester may do in it (they can never share it) | `temporary_schema.privileges` (under `jobs:`): never `MANAGE` or `ALL_PRIVILEGES`, the build refuses them |
| Who owns new schemas | `catalog_owner` (under `jobs:`). Workspace folders are made by hand for now: `folder_root` is where the approvals app tells admins to create them |

Never change `name`, `approvals.name` or `database.project_id` (they name the apps and the database: changing them makes new ones). Stop and say a maintainer should plan it.

## 3. A pull request: `config/self-service/hub.yaml`

The hub: the central workspace where both apps and their database run.

| They want to... | Key |
| --- | --- |
| Who may open the self-service app | `hub.users_group` (`users` = everyone in the hub) |
| Who may open the approvals app (the approvers) | `hub.approvals_group` (`null` = workspace admins only) |
| People who may read the requests' data | `database.readers` (emails) |

**Setting the app up for the first time** (the hub's `host` is still `null`): follow `docs/SETUP.md`, step 12, with them. In short, two pull requests:
1. `hub.name` and `hub.host` (the hub's per-workspace URL), the groups above, and a look at `app.yaml`. The merge binds each workspace's catalog to the hub and creates the apps, their database and a schema job per workspace, in the hub; the **Deploy the app** run's log ends with the two apps' IDs.
2. Those IDs into `app_ids`. The merge lets the apps browse every workspace's catalog (to say whether a schema name is taken).

Check step 12's **Before you start** with them first (serverless, Apps and Lakebase in the hub; the pipeline's identity is admin there).

## 4. A new business unit

A business unit is a managed workspace (its `prefix`, upper case). To add one, add its workspace: the skill **add-workspace**. Its merge deploys its schema job, the daily cleanup covers its catalog too, and the app offers it on the next deploy. To leave a workspace out of the app: `self_service: false` in its file (the skill change-one-workspace).

## 5. The temporary schema cleanup (nothing to edit)

One job in the hub, **Temporary schema cleanup**, drops every temporary schema whose `cd_expires` date has passed, once a day at 06:00 UTC, in every business unit's catalog. It is deployed with the apps; there is no setting to change but `temporary_schema.days` (above).

| They want to... | Tell them |
| --- | --- |
| See what it deleted, whose and how many tables | In the hub, Jobs > **Temporary schema cleanup** > its latest run: the summary is at the top |
| See what it would delete, without deleting | **Run now with different parameters**, `dry_run` = `true` (a workspace admin) |
| Keep a temporary schema longer | In the app, on their temporary schema: **Extend temporary schema** (7 days). It waits in the approvals app, and the schema is not deleted while it waits; rejected, it is deleted at the next cleanup if its date has passed. The reminder shows on every page 3 days before. Keeping one as a project schema is not offered for now: copy what they need into a project schema |
| Why their old personal schema is now temporary | Personal schemas are not offered any more: the cleanup made each one temporary (deleted 30 days later unless more time is approved or it is kept) |

## 6. Edit, read back, deploy

1. Change only what was asked, keeping the comments; two spaces per level, no tabs.
2. Read it back in plain words ("project schemas will no longer wait for an approver").
3. Hand over to the skill **pull-request-from-databricks**. The pull request shows an **App plan** of what the deploy changes; after the merge, **Deploy the app** redeploys both apps (about two minutes).
