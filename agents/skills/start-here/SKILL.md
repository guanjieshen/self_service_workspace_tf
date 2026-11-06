---
name: start-here
description: Use when someone asks for anything about this repository, the workspaces or the Citizen Development apps, however it is worded, and use it first when unsure ("fix the app", "user can't see their schema", "add a workspace", "change the banner", "deploy failed", "help"). Turns a short or vague request into a precise task, asks at most two questions, writes the plan in plain words and gets a yes, then hands over to the right skill. Changes nothing itself.
---

# Start here: turn the request into a precise task

The person may be new to Databricks, git and software. They may write a few words ("schema broken"). Your job is to understand what they need, say it back precisely, and send it to the right skill, so the work follows the same process every time.

## 1. Understand it

Read the request and decide which of these it is. If it is unclear, ask **at most two short questions**, with examples to pick from ("Is this about one person's request, or the whole app?"). Ask for facts you cannot look up: who, which workspace or business unit, what they saw (the exact message or a screenshot), when.

| They want... (examples of how they may say it) | It is | Hand over to the skill |
| --- | --- | --- |
| To know why something went wrong ("request failed", "schema gone", "can't log in", "app down", "user says X") | A problem to investigate, read only | **investigate-a-problem** |
| A red check or a failed deploy fixed ("PR is red", "deploy failed", "pipeline broke") | A failed run | **fix-a-failed-check-or-deploy** |
| To know what a pull request will do, or whether it is safe ("is this safe to merge?", "what does this plan mean") | A plan to read | **read-a-plan** |
| A temporary schema asked about or changed ("extend X's schema", "why was it deleted", "allow 2 per person") | Temporary schema support | **support-a-temporary-schema** |
| A setting of the apps changed (banner, links, branding, the AI model, who approves, the guided tour) | An app setting | **update-self-service-app** |
| A new workspace managed | A new workspace | **add-workspace** |
| One workspace's settings changed (its groups, warehouse, sharing groups) | One workspace | **change-one-workspace** |
| Every workspace's defaults changed | All workspaces | **change-all-workspaces** |
| Genie Code's own instructions or skills in the workspaces changed | Genie Code content | **change-genie-code** |
| What the apps store changed (a new field, a new table) | The database | **change-the-database** |
| The apps' or jobs' code changed (a new card, form, page, job behaviour) | Framework code | **change-the-app-code** |
| A newer release of the framework installed | An upgrade | **upgrade-to-a-new-release** |

## 2. Write the precise task, and get a yes

Before anything is done, write back, in plain words:

1. **What they asked for**, in one sentence, precisely ("Give ana@contoso.com's temporary schema `gsp_citizen_dev.cd_tmp_sales` 7 more days").
2. **What will happen**: which skill, which files or settings change (or "nothing changes: we only look"), and who must approve (an approver in the admin app, a code owner on the pull request).
3. **What could go wrong**, if anything (lost access, data deleted, every workspace affected), and how it is undone.
4. **What they will see when it is done** (a merged pull request, a new date on the card, an answer).

Ask: **"Shall I go ahead?"** Wait for a clear yes. If they change the request, write it again.

## 3. Hand over

Follow the chosen skill from its start, with the precise task as its input. When the work changes files, it ends with the skill **pull-request-from-databricks**: nothing reaches a workspace until a reviewed pull request is merged.

## Rules for every request

- **Never change a workspace, a job, the database or a setting by hand** to "just fix it": changes go through the admin app's Settings (the skill **update-self-service-app** says which) or a pull request.
- **Never paste a password, token or secret** anywhere.
- **If the request is about framework code** (anything outside `config/` and `.github/CODEOWNERS`), it also updates the guides in `agents/` and `CHANGELOG.md` (the skill **change-the-app-code**; `AGENTS.md`, "Keep the guides and the changelog true").
- **When unsure, say so**, and ask a platform admin rather than guess.
