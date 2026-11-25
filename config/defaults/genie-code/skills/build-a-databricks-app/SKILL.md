<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-a-databricks-app/ in
every workspace, with deploy_app.py and template/ (the starter app) next to it. Terraform fills in
{prefix}, {WAREHOUSE}, {WORKSPACE_TAGS_JSON} and {CATALOG} from this workspace's configuration;
the other files are deployed as they are.
-->
---
name: build-a-databricks-app
description: Use when someone wants to build, change, deploy or remove a custom web app (a Databricks App), such as a tracker, a request or review form, or an internal tool over their data, that reads data through the SQL warehouse or keeps its own data. Builds it in React from a tested starter, with Lakebase for its data, named, tagged and charged the way this workspace requires. For charts over data alone, an AI/BI dashboard is simpler: suggest that first.
---

# Build a Databricks App

People one-shot apps here: make it **work and look good the first time**, for few tokens. Don't write the plumbing: the starter (`template/`) and `deploy_app.py` already do the server, the SQL warehouse, the database, the build and the deploy, tested. You write the app's own routes and screens, and its two documents.

**Read only what you need:** this file, then the starter's `AGENTS.md`, `server/index.mjs`, `src/App.jsx` and `src/components/ui.jsx`. Don't read `deploy_app.py` or `server/databricks.mjs`: you call them, you don't change them.

## 1. The brief: one message, then build

If they describe a problem rather than an app ("our inspections live in spreadsheets"), or aren't sure what it should do, use the skill **plan-a-databricks-app** first: it interviews them and hands back a brief. Then propose an answer for each row yourself, from what they asked and what you can see, and send it as **one message** ending "Shall I build it? Change anything you like." Don't write code before they agree. In plain words: say "the app's own database" (not Lakebase) and "the table's full name" (not `catalog.schema.table`).

| Propose | Why |
| --- | --- |
| **What it's for, and who uses it** (one sentence) | The app's description and its first screen |
| **The data it reads:** each table's full name | Queries run **as the person using the app**: anyone who can't read a table sees an error. Check you can read it (`DESCRIBE TABLE`) and use its real column names. Their workspace's catalog is `{CATALOG}` |
| **The data it keeps** (notes, statuses, requests...), or none | Kept in the app's own database. None: no database (`lakebase=False`) |
| **Its screens and actions** | Two to four screens to start, as tabs |
| **Its name** | It becomes **`{prefix}-app-<name>`** (lowercase letters, digits and dashes; 30 characters in all): write the full name |
| **Where its code goes** | `/Workspace/Users/<their email>/apps/{prefix}-app-<name>` |

## 2. Start: a new app, or the one that exists

```python
import sys; sys.path.append("/Workspace/.assistant/skills/build-a-databricks-app")
from deploy_app import new_app, deploy, remove
new_app("<the folder>")   # a new app only
```

- **A new app:** run the cell above (in a notebook, on serverless). It copies a working app into the folder.
- **An app that exists** (its folder has a `package.json`): don't run `new_app()`. Read its `AGENTS.md` first, then change it. **If `AGENTS.md` says it's in production,** don't use `deploy()`: change its files, then deploy it from its bundle (the skill **take-an-app-to-production**, step 4).

## 3. Build it

Change `server/index.mjs` and `src/`, following the rules in the starter's `AGENTS.md` (they are this app's rules from now on):

- **Replace the examples** (the taxi trips, the notes, the `app.notes` table) with the app's own, and delete what it doesn't use. No database: delete `migrate()`'s tables, every `db.query` route, and the notes screen.
- **Routes:** `sql(statement, {name: value}, userToken(req))` with named parameters (`:name`), never values pasted into SQL; `db.query(text, [values])` with `$1`; every route in `handle()`; check input on the server and `throw bad("...")` with a message people can act on; `intParam()` for numbers from the query string.
- **The database's tables:** in the `app` schema, made in `migrate()` with `CREATE TABLE IF NOT EXISTS`; a later change adds to it (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`), never drops.
- **Screens:** tabs in `App.jsx` (`Tabs`), each a function; a long one moves to `src/pages/<Name>.jsx`. Only `ui.jsx`'s components; every data card through `Async`; `statValue()` for a `Stat`. Set `APP_TITLE`.
- **Design:** the tokens in `styles.css` only, no inline styles, no other UI or CSS library; one primary button per card; short, plain, sentence-case labels; numbers right-aligned.
- **Clean code:** small functions, clear names, a short comment where the why isn't obvious, no dead code, no secrets or hosts in the code. No new npm package unless the app can't work without one. Never a `package-lock.json`.
- **Document it:** fill in the starter's `README.md` (for people) and `AGENTS.md` (for whoever changes it next: the brief, the files, a line in Changes) from the brief. On every later change, update both.

## 4. Deploy

```python
deploy(prefix="{prefix}", name="<name>", folder="<the folder>",
       description="<what it's for, one sentence>", warehouse="{WAREHOUSE}",
       tags={WORKSPACE_TAGS_JSON}, lakebase=True)   # lakebase=False when it keeps nothing
```

Tell them it takes **5 to 10 minutes** the first time (it prints what it is doing). It applies this workspace's standards for them: the name `{prefix}-app-<name>` for the app and its database; their **default usage policy** on both (so the costs go to their business unit); the default SQL warehouse; the database at its smallest size, paused after 5 minutes unused, tagged with the workspace's tags and `APP`, `OWNER`, `CREATED_WITH: genie-code` and `EXPIRES`. Run it again after every change: it updates, never duplicates, and moves `EXPIRES` 30 days on.

It also writes `databricks.yml`: the app and its database as a Databricks Asset Bundle, so it can move into Git and CI/CD when it's ready (the skill **take-an-app-to-production**).

Then **they** open the URL it prints (you can't). The first visit asks them to allow the app to use their data: that's expected. Ask them to check each screen and tell you what they see.

## 5. When something goes wrong

Ask them for the logs: the app's URL + `/logz` (its first line says which settings it has). Then:

| They see, or `deploy()` says | It means | Do |
| --- | --- | --- |
| `The deployment FAILED: Error installing packages` | A bad `package.json` | Fix the package's name or version; deploy again |
| `The deployment FAILED` with another message, or **App Not Available** | The build or the server failed | `/logz`: usually a syntax error in `server/` or `src/`; fix, deploy again |
| `This app can't read data for you yet` | The person hasn't allowed the app, or its user authorization is off | They reload and allow it; if it lasts, deploy again |
| `INVALID_LIMIT_LIKE_EXPRESSION` or a type mismatch | A number passed as text | Pass numbers as numbers (`intParam()`) |
| `PERMISSION_DENIED`, `TABLE_OR_VIEW_NOT_FOUND` | That person can't read the table (queries run as them) | They ask its owner (Catalog Explorer > Request access): never work around it |
| `"database": "starting"` in `/api/health` | The database was paused or is still being made | Wait a minute and reload |
| `The name ... is taken by an app you can't change` | Someone else's app has that name | Propose another name, and confirm it |
| `Warning: no usage policy applies to you` | Its costs aren't charged to their business unit | They ask their platform admin; the app still works |
| `TimeoutError: ... Run deploy() again` | Something was slow to start | Run `deploy()` again: it carries on |

## 6. Remove it

When it's no longer needed (admins may remove it after its `EXPIRES` date), and with their yes, because it deletes the app's data:

```python
remove(prefix="{prefix}", name="<name>")
```

Then delete its folder. A removed database is kept for 7 days: deploying the same name in that time brings it back, with its data.
