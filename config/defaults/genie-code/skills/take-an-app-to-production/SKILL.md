<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/take-an-app-to-production/ in
every workspace, with ci/github-actions-deploy.yml next to it. Moves an app made with the skill
build-a-databricks-app from "deployed from a notebook" to "deployed from its bundle", in Git and
CI/CD when there is one.
-->
---
name: take-an-app-to-production
description: Use when an app made with build-a-databricks-app is ready for other people to rely on, or someone asks to put an app in production, in Git, in a repository, under CI/CD or GitHub Actions, or to have its changes reviewed before they go live. Moves it onto its Databricks Asset Bundle (databricks.yml, already in its folder) without recreating it or losing its data, with or without a Git repository.
---

# Take an app to production

An app made with **build-a-databricks-app** already carries its definition: `databricks.yml` (a Databricks Asset Bundle) describes the app and its database exactly as `deploy()` made them. Production means **the bundle owns the app from now on**: changes are made in its files and deployed from the bundle (by a person, or by CI/CD after a review), never with `deploy()` again.

Explain each step in plain words and do one at a time. Commands run in the Databricks **web terminal** (Compute > the app's folder > **Terminal**, or any web terminal) from the app's folder.

## 1. Check it is ready

- Its folder has `databricks.yml`, `AGENTS.md` and `README.md`, and `AGENTS.md` describes the app as it is now. If `databricks.yml` is missing (an app made before this skill existed), run `deploy()` once more (build-a-databricks-app, step 4): it writes it.
- The app works today, and its owner agrees.

## 2. Where its code lives

| They have | Do |
| --- | --- |
| **A Git repository** (GitHub, Azure DevOps, GitLab...) | Make a **Git folder** of it in Databricks (Workspace > Create > Git folder), copy the app's files into a folder of it (for example `apps/{prefix}-app-<name>/`, without `node_modules` or `dist`), then commit and push from the Git folder. From now on, that Git folder is the app's code |
| **No repository yet** | Keep the app's folder. Everything below works from it, and moving it into Git later is a copy |

## 3. Give the app to its bundle

From the app's folder (the Git folder copy, if there is one), in the web terminal:

```bash
databricks bundle validate
databricks bundle deployment bind database projects/{prefix}-app-<name> --auto-approve   # skip if it keeps no data
databricks bundle deployment bind app {prefix}-app-<name> --auto-approve
databricks bundle plan
```

The plan must say **0 to add, 0 to change**: the bundle describes what exists. Anything else, stop and read it with them: never let it recreate the database (its data would be lost).

## 4. Production settings

Edit `databricks.yml` (it's the app's definition now), then show them the diff:

- **Tags:** set `OWNER` to the team's group or mailbox, not one person. Ask whether it should be left on (people rely on it every day: usually yes) and set the app's `LEAVE_ON` tag to it: run `deploy()` once more with `leave_on=True` **before** this step (it is the last time `deploy()` runs), or change the tag with the entity tags API.
- **Who can use it:** under the app, add `permissions:` with the group of its users (`level: CAN_USE`) and its owners (`level: CAN_MANAGE`), as Entra ID groups.
- **AGENTS.md:** add "In production since <date>: change it through its bundle (and Git), never with deploy()" and a line in Changes.

Then deploy it from the bundle and start the new version:

```bash
databricks bundle deploy
databricks bundle run app
```

## 5. CI/CD, if they have a repository

A ready workflow for **GitHub Actions** is next to this file: `ci/github-actions-deploy.yml`. On a pull request it builds the page and validates the bundle; on a merge to `main` it deploys and starts the app. Copy it to the repository's `.github/workflows/`, set `APP_DIR` in it to the app's folder, and set up its identity with the platform team:

- **A service principal** that deploys it (never a person's account), with **Can manage** on the app and the database (or: bind and deploy once as that service principal).
- **Its sign-in from GitHub:** a federation policy for the repository (no secret to store), or an OAuth secret kept as a repository secret. The workflow names both.

Other CI systems (Azure DevOps, GitLab) run the same three commands: `npm install && npm run build`, `databricks bundle validate`, then `databricks bundle deploy && databricks bundle run app`.

## Never

- Never run `deploy()` (build-a-databricks-app) on an app in production: it has one owner, its bundle.
- Never let a plan delete or recreate the database. `databricks bundle destroy` deletes the app and its data: only with a clear yes, as with `remove()`.
