# Working on <APP NAME>

<One or two sentences from the design brief: what the app is for, and who uses it.>

> **Start here.** Read this file, then only the files you are changing. Change the app with Genie
> Code's skill **build-a-databricks-app**: it knows how this app is built and deployed.

## The brief

| | |
| --- | --- |
| **The app** | `<prefix>-app-<name>`: <its URL> |
| **For** | <who uses it, and what they do with it> |
| **Reads** | <the tables, `catalog.schema.table`, and what it reads from each> |
| **Keeps** | <what it saves in its own database (the `app` schema), or "nothing"> |
| **Screens** | <each screen, and what people do there> |
| **Code** | `<the folder in the workspace>` |
| **Owner** | <who to ask about it> |

## How it works

```
browser ──► src/App.jsx (React, the screens) ──► /api/... ──► server/index.mjs (the routes)
                                                                 │
                         sql(...)  ──► the SQL warehouse, as the signed-in person (their access)
                         db.query(...) ──► the app's Lakebase database (the app's own data)
```

Databricks Apps builds it on every deploy (`npm install`, then `npm run build` makes `dist/`), then
runs `npm run start` (`node server/index.mjs`).

## Files

| File | What it is | Change it? |
| --- | --- | --- |
| `server/index.mjs` | The API: one route per thing the page needs, and the database's tables (`migrate()`) | Yes |
| `src/App.jsx` | The screens (tabs) | Yes |
| `src/pages/<Name>.jsx` | A screen, when `App.jsx` grows past a few hundred lines | Yes |
| `src/components/ui.jsx` | The shared components | Add one when no existing one fits |
| `src/styles.css` | The design tokens and each component's styles | Add a component's styles; change a token to change the look |
| `src/api.js` | `call()` and `useApi()`: how the page talks to the server | No |
| `server/databricks.mjs` | The SQL warehouse and Lakebase connections | No |
| `app.yaml` | How the server finds the warehouse and the database: written by `deploy()` | No: deploy again instead |
| `databricks.yml` | The app and its database as a Databricks Asset Bundle: written by `deploy()`; in production, the app's definition | Before production: no. In production: yes, through Git |
| `package.json` | The packages | Only to add a package the app can't do without |

## Rules

- **SQL:** `sql(statement, params, userToken(req))` with named parameters (`:zip`), never values pasted into the statement. Full table names, aggregated in SQL, always a `LIMIT`. Numbers stay numbers (a `LIMIT` needs one: `intParam()`).
- **The database:** `db.query(text, [values])` with `$1` placeholders. Tables live in the `app` schema. A new table or column is added to `migrate()` (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`): never change or drop what is there.
- **The API:** every route in `handle()`; check every input on the server, and `throw bad("...")` with a message people can act on.
- **The screens:** only the components in `ui.jsx`; every data card through `Async` (loading, empty, error); `statValue()` for a `Stat`; one primary button per card; short, plain, sentence-case labels.
- **The look:** the tokens in `styles.css` only, no inline styles, no other UI or CSS library.
- **Code:** small functions with clear names, a short comment saying why (not what) where it isn't obvious, no dead code, no secrets or hosts in the code. Never add a `package-lock.json`.
- **This file and README.md** are part of every change: update the brief, the files table and the changes log.

## Deploy and remove

In a notebook (serverless):

```python
import sys; sys.path.append("/Workspace/.assistant/skills/build-a-databricks-app")
from deploy_app import deploy, remove
deploy(prefix="<prefix>", name="<name>", folder="<the folder>", description="<the description>",
       warehouse="<the warehouse>", leave_on=<True or False: ask>, tags=<the tags>, lakebase=<True or False>)
remove(prefix="<prefix>", name="<name>")   # deletes the app and its data
```

The logs: the app's URL + `/logz`. Its first line says which settings it has.

**To production** (others rely on it, changes reviewed first): Genie Code's skill **take-an-app-to-production** moves it onto its bundle (`databricks.yml`), in Git and CI/CD when there is a repository. After that, it is deployed only from its bundle, never with `deploy()`.

## Changes

| Date | Change |
| --- | --- |
| <date> | Made with Genie Code: <the first version, in one line> |
