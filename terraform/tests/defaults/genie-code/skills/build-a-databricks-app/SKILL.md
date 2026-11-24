<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-a-databricks-app/ in
every workspace, with deploy_app.py and template/ (the starter app) next to it. Terraform fills in
{prefix}, {WAREHOUSE}, {WORKSPACE_TAGS_JSON} and {CATALOG} from this workspace's configuration.
-->
---
name: build-a-databricks-app
description: Use when someone wants to build, change, deploy or remove a web app (a Databricks App) (a dashboard, a tracker, a form, a tool) that reads data through the SQL warehouse or keeps its own data. Builds it in React from a tested starter, with Lakebase for its data, named, tagged and charged the way this workspace requires.
---

# Build a Databricks App

People one-shot apps here: make it **work and look good the first time**. Don't write the plumbing: the starter (`template/`) and `deploy_app.py` already do the server, the SQL warehouse, Lakebase, the build and the deploy, tested. You write the app's own screens and routes.

## 1. The design brief: ask first, build after

Don't write code until you have these, and they agreed to your summary. Ask at most two questions at a time, in plain words; suggest an answer when you can.

| Ask | Why |
| --- | --- |
| **What it's for, and who uses it** (one or two sentences) | The description, and what the first screen shows |
| **The data it reads:** which tables (`catalog.schema.table`) | Queries run **as the person using the app**: anyone who can't read a table sees an error for it. Check you can read them (`DESCRIBE TABLE`) and use real column names |
| **The data it keeps** (notes, statuses, requests...), or none | Its own Lakebase database. None: no database |
| **The screens and actions:** what people see and do | At most three or four screens to start |
| **Its name** | It becomes `{prefix}-app-<name>`: lowercase letters, digits and dashes, 30 characters in all. **Say the full name and confirm it** |
| **Where its code goes** | A new folder; suggest `/Workspace/Users/<their email>/apps/{prefix}-app-<name>` |

Then write the brief back in five lines and ask "Shall I build it?".

## 2. Start from the starter

In a notebook cell (serverless):

```python
import sys; sys.path.append("/Workspace/.assistant/skills/build-a-databricks-app")
from deploy_app import new_app, deploy, remove
new_app("<the folder>")
```

It copies a working app: `server/index.mjs` (the API), `server/databricks.mjs` (the SQL warehouse and Lakebase: don't change it), `src/App.jsx` (the page), `src/components/ui.jsx` (the components), `src/styles.css` (the design tokens).

## 3. Build it

Change only `server/index.mjs` and `src/` (add pages as `src/pages/<Name>.jsx`). Keep the starter's patterns:

- **SQL:** `sql(statement, params, userToken(req))`, with **named parameters** (`:zip`), never values pasted into the SQL. Numbers and booleans keep their type (a `LIMIT` needs a number). Full table names. Aggregate in SQL, not in the browser; always `LIMIT`.
- **Lakebase:** `db.query(text, [values])` with `$1` placeholders. Tables in the `app` schema, made in `migrate()` with `CREATE TABLE IF NOT EXISTS`; a new column: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Record who did what with `who(req)`.
- **The API:** every route wrapped in `handle()`; check input on the server (required, length, allowed values) and throw plain-English messages.
- **The page:** build from `ui.jsx` (`Shell`, `PageHead`, `Card`, `Stat`, `DataTable`, `Button`, `Field`, `Async`, `Empty`, `ErrorNote`); call the API with `useApi` and `call`. Every data card shows its loading, empty and error states (`Async`).
- **Design:** the tokens in `styles.css` only, no inline colours or sizes, no other UI or CSS library. One primary button per card. Plain, short labels (sentence case). Numbers right-aligned in tables. A new component goes in `ui.jsx`, built from the tokens.
- **Clean code:** small functions, clear names, no dead code, no secrets or hosts in the code, no new npm packages unless the app can't work without one. Never add a `package-lock.json`.

## 4. Deploy

```python
deploy(prefix="{prefix}", name="<name>", folder="<the folder>",
       description="<one sentence: what it's for>", warehouse="{WAREHOUSE}",
       tags={WORKSPACE_TAGS_JSON}, lakebase=True)   # lakebase=False when it keeps no data
```

It takes 5 to 10 minutes the first time. It applies this workspace's standards: the name `{prefix}-app-<name>` for the app and its database; the person's **default usage policy** on both; the default warehouse; Lakebase at its smallest size, **suspended after 5 idle minutes**, tagged with the workspace's tags and `APP`, `OWNER`, `CREATED_WITH: genie-code` and `EXPIRES` (30 days). Run it again after every change: it updates, never duplicates.

Then open the URL it prints (the first visit asks the person to allow the app to use their data: that's expected) and check each screen.

## 5. When something goes wrong

Read the logs first: the app's URL + `/logz`. Its first line says which settings it has.

| You see | It means | Do |
| --- | --- | --- |
| Deploy FAILED: **Error installing packages** | A bad `package.json` or a `package-lock.json` | Fix the dependency; delete the lock file; deploy again |
| **App Not Available** | The server didn't start | `/logz`: usually a syntax error in `server/`; it listens on `DATABRICKS_APP_PORT` |
| `INVALID_LIMIT_LIKE_EXPRESSION` or a type mismatch | A parameter passed as text | Pass numbers as numbers |
| `PERMISSION_DENIED` / table not found | The person can't read that table (queries run as them) | They ask the table's owner for access (Catalog Explorer > Request access); not something to work around |
| `Lakebase is not ready` in the logs | The database was waking up or still being made | Wait a minute and reload; deploy again if it lasts |
| **Name already taken** | Another app has it | Choose another name, and confirm it |
| A blank page | The build failed or `App.jsx` threw | `/logz` for the build; the browser console for the page |

## 6. Remove it

When it's no longer needed (and before its `EXPIRES` date), with their yes, because it deletes the app's data:

```python
remove(prefix="{prefix}", name="<name>")
```

Then delete its folder.
