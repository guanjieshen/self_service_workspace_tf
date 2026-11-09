---
name: fix-a-failed-check-or-deploy
description: Use when a pull request has a red check (Format and validate, Tests, Changelog for framework changes, a Plan, App plan, Database tests) or a Deploy run failed after a merge (an Apply, Deploy the app). Reads the run's log, says which step failed and why in plain words, and proposes the smallest fix, made as a new commit or pull request. Never re-runs an apply by hand, skips a check or changes a workspace directly.
---

# Fix a failed check or deploy

The person may only know "it's red". Find the run, read its log, explain it in plain words, then fix the cause through the normal process: a change in the Git folder and the skill **pull-request-from-databricks**. Never work around a check.

## 1. Find the failed step

GitHub > the repository > the pull request > **Checks** (or **Actions** > the **Deploy** run for a merge). Open the red job, then the red step: its last lines say what went wrong. Copy the error.

## 2. What it means, and the fix

| Red | Usually | Fix |
| --- | --- | --- |
| **Format and validate**: `terraform fmt` | A Terraform file's spacing | Ask a maintainer to format it, or fix the spacing the error shows |
| **Format and validate**: `workspaces.py check` | Two workspace files clash (host, prefix, catalog name) | Make the new workspace's values unique (the skill **change-one-workspace**) |
| **Format and validate**: **Changelog for framework changes** | Framework code changed without a `CHANGELOG.md` entry | Add the entry under **Unreleased** and update the guides it names (the skill **change-the-app-code**, step 5) |
| **Tests** | A test no longer passes: the log names the test and the file | Read the test's name: it says the rule. Fix the change, not the test, unless the rule itself changed on purpose |
| **Plan &lt;workspace&gt;** | Something outside the repository: a group not in the account, the pipeline's identity not an admin in the workspace, a catalog name taken | The plan comment's top says which; it is fixed outside GitHub (Entra ID, the Databricks account), then **Re-run jobs** |
| **App plan** / **Deploy the app** | The app's settings (`config/self-service/`) are wrong, or a migration failed | The log names the setting or the migration: fix it in a pull request (a migration that failed never ran: see `agents/database.md`, section 6) |
| **Database tests** | A migration or `store.py` does not work on Postgres | `agents/database.md`, section 4: the skill **change-the-database** |
| **Apply &lt;workspace&gt;** after a merge | The apply hit something the plan could not see | Read the error; fix in a new pull request, or (if it was a temporary outage) **Re-run failed jobs** on that Deploy run |

## 3. Make the fix

Explain the cause and the fix in one or two sentences, and get a yes. Make the change in the Git folder, then the skill **pull-request-from-databricks**: the checks run again by themselves.

## Never

- Never re-run an apply from a laptop, add a label to skip a check, or merge with a red required check.
- Never delete or edit a test to make it pass, unless the rule it checks was changed on purpose (say so in the pull request).
