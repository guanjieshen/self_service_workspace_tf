<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/start-a-project/ in every
workspace. The front door for anything bigger than a question: it plans the work and sets up the
project, then hands each part to the skill for it. It holds this organization's rules; Genie Code
already knows how to build each part in Databricks.
-->
---
name: start-a-project
description: Use when someone wants to build something in this workspace that is more than a quick query, such as "help me track inspections", "I need a report that updates daily", "build me a tool for my team", or names several things at once (data, a pipeline, a dashboard, an app, a Genie space). Interviews them, finds the data, splits the work into parts in the right order, sets up the project folder, its name and its application ID, and hands each part to the right skill.
---

# Start a project

The people here know their business and are often not engineers. Understand the work, find what already exists, then build the smallest useful thing. **Ask, don't guess:** two questions at a time at most, each with a suggested answer, in plain words.

## 1. The goal, in their words

Ask what they're trying to achieve, who it's for, and what they do today (a spreadsheet, an email, a report). Play it back in a sentence. If an app is part of it, the skill **plan-a-databricks-app** has the questions for it.

## 2. Find the data first (reuse before you build)

- Search with **`/findTables <words>`** (and `/findQueries`). Start in `{CATALOG}`, this workspace's catalog.
- For each table that might fit: **check they can read it** (`SELECT ... LIMIT 1`, as them), **who owns it** and **how fresh it is** (`DESCRIBE TABLE EXTENDED`, `DESCRIBE HISTORY`). Show them what you found and ask "Is this the one?".
- **They can't read it:** they ask its owner, in Catalog Explorer > **Request access**. Never copy data around a permission.
- **Nothing fits:** either they build it (the part below: a pipeline) or it's a dataset TIS provides (the skill **ask-tis**). Ask which.

## 3. Split it into parts, in order

| Part | Build it with | Only when |
| --- | --- | --- |
| **Data:** tables cleaned and joined for this project | **build-a-pipeline** | The data they need isn't already there in the shape they need |
| **A dashboard** or **a Genie space** | **build-a-dashboard-or-genie-space** | They want to look at, filter or ask questions of the data. Often the whole answer: suggest it before an app |
| **An app:** people record, update, approve or track something | **plan-a-databricks-app**, then **build-a-databricks-app** | A dashboard isn't enough |
| **Something TIS provides:** a production dataset, a connection to another system, network access to an outside service, a service principal | **ask-tis** | They can't, or shouldn't, do it themselves |

Data first, then what reads it. For each part, decide with them: **reuse** what exists, **build** it, or **ask TIS**. Build the smallest useful version of each, then improve.

## 4. Set up the project

| | The standard |
| --- | --- |
| **Its name** | `<prefix>-<project>`, lower case with dashes, where `<prefix>` is {PREFIX} in lower case (for example `gtm-well-tests`). Confirm it |
| **Its folder** | `/Workspace/Users/<their email>/projects/<prefix>-<project>/`, one folder per project: `README.md`, `AGENTS.md`, then a folder per part (`pipeline/`, `dashboards/`, `app/`, `notebooks/`). One folder moves into Git as one repository |
| **What its parts are called** | `<prefix>-<kind>-<name>`: `<prefix>-pipeline-<name>`, `<prefix>-job-<name>`, `<prefix>-dashboard-<name>`, `<prefix>-genie-<name>`, `<prefix>-app-<name>` |
| **Its tables** | Their **temporary schema** to try things (one per person; made with their Azure PIM account, `azure-...`; **deleted with everything in it** on its `cd_expires` date). A **permanent schema** to keep the work, requested in the self-service app (the skill **ask-tis**). Move the tables there **before** anything is scheduled or shared |
| **Its application ID (APPID)** | The ID of the business application this work belongs to, in the company's application list (CMDB): it says whose budget pays. The workspace's (already on its usage policy: {WORKSPACE_TAGS}), unless they name their own. If the workspace's is `NONE`, ask for one. Ask once; use it on every part |

Write the project's `README.md` (for people: the goal, who it's for, its parts and where they are) and `AGENTS.md` (for whoever changes it next: the goal, the data found, each part with its name and status, the APPID, the decisions, and a table of what was asked of TIS). Keep both up to date as each part is built.

## 5. Build each part

Hand each part to its skill, in order, with what you've learned. After each one: show them what was made and where, update the project's `AGENTS.md`, then go to the next. To see or clean up what they've made, the skill **my-projects**.
