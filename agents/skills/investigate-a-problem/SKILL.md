---
name: investigate-a-problem
description: Use when someone reports that something does not work or did not happen as expected: a request that failed or is stuck, a schema that is missing or was deleted, a person who cannot open the app or see their schema, the admin app or the self-service app down, a job that failed. Looks, never changes: finds the request, its job run, the schema's tags, the cleanup's report and the apps' health, explains the cause in plain words, and proposes the fix (handing over to the right skill to make it).
---

# Investigate a problem (read only)

The person may describe it vaguely ("it's broken"). You only **look**: nothing you do here changes anything. At the end, say the cause in one or two plain sentences and the fix, and hand over to the right skill to make it (any change ends with the skill **pull-request-from-databricks**, or a step in the admin app).

## 1. Get the facts (at most two questions)

Who (their email), what they tried (which card or form), what they saw (the exact message, or a screenshot), and when. The business unit is the prefix shown at the top right of the app (for example GSP).

## 2. Look, in this order

| Look at | Where | What it tells you |
| --- | --- | --- |
| **Their request** | The admin app (its header says Admin) > **All requests**, search their email; open the request | Its state (Pending approval, Reply needed, Rejected, In progress, Completed, Failed), the conversation, who decided and when |
| **Its job run** | On the request: **Open job run** (it opens in the hub) | Whether the job ran, and its error in the run's output (for example "already exists and is not ana's", "You already have 1 temporary schema") |
| **The schema** | Catalog Explorer in their workspace > the catalog (for example `gsp_citizen_dev`) > the schema > **Details** (tags) and **Permissions** | `cd_user` (whose), `cd_schema_kind` (temporary, project, team), `cd_expires` (deleted after), `cd_pending_request` (held while an extension waits), and who has which rights |
| **The daily cleanup** | The hub > Jobs > **Temporary schema cleanup** > the run of that day > its output | Its summary: what it deleted (whose, how many tables), kept, failed, and which old personal schemas it made temporary |
| **The apps** | The hub > Compute > Apps > `cd-self-service` (or `cd-approvals`) > **Logs**; and the app's address + `/healthz` | Whether the app runs, and whether it reaches its database and its jobs |
| **The last deploy** | GitHub > the repository > **Actions** > the latest **Deploy** run | Whether the last change deployed, and where it stopped |

## 3. Common causes

| They see | Usually | The fix |
| --- | --- | --- |
| "No workspace offers schemas yet" / a form says there is no workspace | The workspace's job is not deployed yet, or its Terraform failed | The skill **fix-a-failed-check-or-deploy** |
| A request is "Pending approval" for a long time | No approver has decided | An approver opens it in the admin app (Pending Approvals) |
| "You already have N temporary schemas" | At their limit | Wait for one to expire, extend or drop one; or raise the limit (the skill **support-a-temporary-schema**) |
| Their temporary schema is gone | The cleanup deleted it after its date (its report says so) | Nothing deletes it early; it cannot be restored from the app. Within 7 days of the deletion, a platform admin may be able to recover the tables (Unity Catalog `UNDROP` for managed tables): ask them |
| They cannot open the app | They are not in the app's users group, or have no persona in their workspace | Their access request (Get started > Request workspace access) |
| "Your business unit can't be read just now" | The database is waking up or down | Wait a minute; if it lasts, `agents/database.md`, section 6 |

## 4. Say what you found

In plain words: **what happened, why, and what fixes it** ("The cleanup deleted `cd_tmp_sales` on Dec 7: it expired on Dec 6 and no extension was asked for."). If a change is needed, hand over to the right skill (the skill **start-here** lists them). Never make the change here.
