---
name: update-self-service-app
description: Use when someone wants to change the self-service app or the approvals app: their links (FAQ, SOPs, persona requests, Discover), the onboarding prompt, a banner, the title, which requests need an approver, the AI check or summary, who may open each app, the jobs' settings (schema prefix and rights, folder location), set the app up for the first time (the hub), or add a business unit to it. Says whether it is a Settings change (no pull request) or a file change, makes the edit, and hands over to pull-request-from-databricks.
---

# Update the self-service app

The person may not know YAML or git. Ask what they want in their own words; at most two questions at a time. **First decide where the change goes**: many need no pull request.

## 1. Settings, no pull request (the approvals app)

These are changed by a platform admin in the **approvals app > Settings** and show in the self-service app within 15 seconds. Point them there; do not edit a file for these.

| They want to... | Settings tab |
| --- | --- |
| A banner across every page (planned maintenance, ...) | **Announcement** |
| The guided tour's prompt (what Genie One is asked the first time someone opens their workspace) | **Onboarding** > Guided tour |
| The links to request Explorer, Builder or Publisher access (for example ServiceNow items), for all business units or one | **Onboarding** > Persona request links, with its **Business unit** selector |
| FAQ links next to each section, or the standard operating procedure behind each task | **Help links** |
| The model that writes new project and team schemas' comments (what each is for, from the reason), or turn them off (empty) | **AI** > Schema comments |
| See who changed what, and when | **Change history** |

## 2. A pull request: `config/self-service/app.yaml`

What people may do, and how the app behaves. Read the key's comment in the file before editing.

| They want to... | Key (under `self_service_app:` unless said) |
| --- | --- |
| The app's title in the header | `title` |
| Which requests wait for an approver | `human_approval` (from `project_schema`, `team_schema`; the others are created straight away) |
| The Validate check on forms (AI advice on the name and reason) | `ai_check`: `"on"` or `"off"` (needs AI Decide in the hub) |
| The approvers' AI summary | `ai_summary.model` (`null` = none) |
| The default model for new schemas' AI comments (admins change it in Settings > AI) | `schema_comment.model` (`null` = off) |
| A wiki link in the header, a short link to the app | `links.wiki`, `links.go_link` |
| The **Add a group to your workspace** card (otherwise Coming soon) | `links.group_request`: their request form's URL |
| The default FAQ links and prompt (Settings overrides them) | `faq.<section>`, `onboarding.prompt` |
| Personal schemas' name prefix or rights | `personal_schema.prefix`, `personal_schema.privileges` (under `jobs:`) |
| Who owns new schemas | `catalog_owner` (under `jobs:`). Workspace folders are off for now (`folder_root` is for when they come back) |

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

A business unit is a managed workspace (its `prefix`, upper case). To add one, add its workspace: the skill **add-workspace**. Its merge deploys its jobs, and the app offers it on the next deploy. To leave a workspace out of the app: `self_service: false` in its file (the skill change-one-workspace).

## 5. Edit, read back, deploy

1. Change only what was asked, keeping the comments; two spaces per level, no tabs.
2. Read it back in plain words ("project schemas will no longer wait for an approver").
3. Hand over to the skill **pull-request-from-databricks**. The pull request shows an **App plan** of what the deploy changes; after the merge, **Deploy the app** redeploys both apps (about two minutes).
