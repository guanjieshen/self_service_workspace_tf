# Working on apps/self-service/

Read the repository's [AGENTS.md](../AGENTS.md) first. This guide is for **maintaining the
self-service web app** (the workspace baseline has its own: [terraform.md](terraform.md)). This is the self-service app:
a Databricks App where people ask for a personal, project or team schema or a workspace
folder, and follow their requests, plus the approvals app (the same code) and the jobs they
run. `docs/design.md` ("The self-service app") is the design; this is how to work on it.

**Two deploy systems, one owner per object.** The app, its database and its jobs are
Databricks Asset Bundles (`bundle/hub/`, `bundle/jobs/`, deployed by `scripts/app_deploy.py`);
the workspaces are Terraform's. The bundles never grant on what Terraform owns (catalogs,
warehouse permissions, usage policies, workspace assignment): what the app needs there,
`terraform/self_service.tf` grants. A test (`test_build.py`) checks the build never emits one.

## How it works

```
browser ──► main.py (FastAPI pages, Jinja templates)  ──►  portal.py (the logic)
                                                               │  as the app's service principal
                                                               ▼
                         each served workspace: its self-service jobs (Jobs API run_now)
                         the job checks the request again and does the work
```

- **It changes nothing itself.** A request is a run of a workspace's job. The job is the
  security boundary; the app's checks are for a good message, not for safety.
- **One central copy, many workspaces.** `config.json` (written by the deployment from the app's
  settings, `config.defaults.yaml`) lists the workspaces.
  The app finds each one's jobs by their `cd_self_service` tag and reads what the jobs say
  about themselves from other tags (`cd_catalog`, `cd_prefix`, `cd_root`). Never hardcode
  what a job's tags say.
- **Every install has its database (Lakebase), and it is the only list of requests.** A
  request is recorded before its job runs; My requests and the approvals app read the
  database, and each request's status from its own job run. There is no second path: if the
  database cannot be read, the page says so (no fallback to the job runs).
- **One request at a time per folder or schema;** different ones run side by side (each
  job allows 20 concurrent runs).

## Files

| File | What it is |
| --- | --- |
| `main.py` | Routes and pages only: who the user is, read the form, call `portal`, render |
| `portal.py` | The logic: discovery, checks, running jobs, describing runs, caches. No web framework |
| `approvals.py`, `approvals_store.py` | The approvals app (the same code, `mode: approvals`): its pages, and its data (`LakebaseStore`; tests use `tests/sample_store.py`) |
| `settings.py` | What approvers change in the approvals app's Settings (links, banner): the list, checks, and how they override app.yaml |
| `checks.py` | The AI check behind Validate on the forms: one AI Decide call, four questions on the name and reason, advice for the requester only |
| `summary.py` | The AI summary for approvers (a foundation model): the only AI an approver reads |
| `templates/` | Jinja pages; `base.html` is the layout, `_icons.html` the icon and approval macros |
| `static/app.css` | The design system (tokens at the top) |
| `static/app.js` | Small enhancements: My requests search and tabs, Validate, polling, filters, loading bar. Every page works without it |
| `app.yaml` | How Databricks Apps starts it |
| `tests/test_portal.py` | Logic and page tests against a fake Databricks client |
| `tests/test_contract.py` | The app and the jobs agree (parameters, rules, naming, tags) |

## Rules

- **Who the user is comes only from Databricks Apps' sign-in** (`X-Forwarded-Email`).
  `PORTAL_USER` stands in for it only when running locally (`DATABRICKS_APP_NAME` unset).
  Never take the user from a form field or query string.
- **A user sees and asks only for their own things.** Every run read is checked against
  who asked (`requester()`); a status page for someone else's run is a 404.
- **Groups come from the user's own token** (`X-Forwarded-Access-Token`, SCIM `/Me`; the
  default user scopes are enough, and naming them explicitly is refused). If that fails,
  offer no groups; never an error page.
- **The job contract:** parameter names, the email, schema, folder and group rules, the
  reserved folder names and how a personal schema is named are the same in `portal.py`
  and in the notebooks (`bundle/jobs/notebooks/`) and their bundle definitions
  (`bundle/jobs/resources/jobs.yml`). Change both in one PR; `test_contract.py`
  fails otherwise.
- **No front-end build, no CDN, no web fonts.** Plain HTML from the server, one CSS file,
  one JS file.
- **One look across both apps.** The self-service app and the approvals app (the same code,
  `APP_MODE=approvals`) share `templates/base.html`, `static/app.css` and the components in
  `templates/_components.html` (`back`, `status_badge`, `facts`, `check_rows`, `empty_state`,
  `chip`). Use a component instead of writing its markup; `tests/test_ui.py` fails if a
  template copies it. A new pattern that both apps need becomes a component. In `app.css`,
  shared rules go under "Shared components", rules for one app's pages under its own section.

## Adding a task

Today a task touches several places (a single definition per task is planned before
SQL warehouses):

1. A job: its notebook in `bundle/jobs/notebooks/`, its definition in
   `bundle/jobs/resources/jobs.yml` (tagged `cd_self_service: <kind>`), its rendering and run
   permissions in `scripts/app_build.py` (`build_jobs`, `jobs_target`), and its notebook's tests
   in `scripts/tests/`.
2. `portal.py`: `TASKS`, `APPROVAL`, a `request_<task>()` method, and the `kind` branches
   in `describe()` and `requester()`.
3. `main.py`: the form and submit routes, and `retry_link()`.
4. `templates/`: the form page (with `_task_header.html`); its card is one line in `cards.py`
   (a link card or a Coming soon card is only that line).
5. Tests in `tests/test_portal.py` and the contract in `tests/test_contract.py`.

## Design

The look, typography and copy rules for both apps: [design.md](design.md). Read it before
changing a template, `static/app.css` or any text people read.

## The database (Lakebase)

- **Code first:** the hub's bundle creates the project, `scripts/app_deploy.py` the database;
  `db/migrations/NNN_name.sql` run once each, in order (`db/migrate.py`, after the bundle
  deploys); `db/grants.sql` runs on every deploy. Never edit a migration that has run: add the next.
- **Migrations are safe by default:** a new version deploys only after the migrations ran
  (`scripts/app_deploy.py` runs each app last). On a first install the apps have no code until
  then (`/healthz` reports the database until the migrations ran). Still, write migrations
  that the version already running can live with (add, then use; never rename in one step).
  A migration with DROP, TRUNCATE or DELETE needs a line `-- destructive: <why it is safe>`,
  or `tests/test_db.py` fails, and the reviewer looks at it on purpose. Try it on the dev
  branch first (`tests/dev_branch.py`).
- **Append-only:** the apps' roles may `SELECT` and `INSERT`, never `UPDATE` or `DELETE`. A
  request's status is the latest state-changing event (`request_status`), never a column.
- **Store only what nothing else keeps; read everything else from its source of truth**
  (decided 2026-10-22). The database holds what the apps create: each request as asked (with
  its BU at the time, the audit record), the AI review and summary, comments, questions,
  replies, decisions, the link to the job run (or that it could not start), and settings
  overrides. Never copied in: a run's status or outcome (the Jobs API), whether a schema or
  folder exists (Unity Catalog, the workspace), a person's groups (SCIM), workspaces and their
  jobs (job tags), users and BUs (Entra, or the BU source). A copy goes stale and needs a sync,
  so it is the exception: only when fetching from the source is extremely convoluted (many
  calls across workspaces, no API for it) or too slow for the page that needs it. Then keep
  the copy in one place, say where it comes from and how it is refreshed, and say why in the PR.
- **Business units come from the BU lookup** (`bu_lookup`, a SQL function: email in, BU out),
  read live on the host's default warehouse and kept an hour, never copied into the database.
  `Portal.workspaces_for` is the one place that decides which workspaces a person's request may
  go to; the forms use it, and `request_schema` / `request_folder` refuse any other.
- **The source of truth can be in any served workspace.** Each workspace has its own Jobs API,
  catalog and SCIM: read a request's run from its own workspace (`row["workspace"]`), never
  the host's, and expect one workspace to be down while others answer (`Workspace.error`).
- **`store.py`** is the app's only code that touches the database (plain SQL). A request is
  recorded *before* its job runs; the run is linked after (`run_started`). **A run's outcome is
  never copied in:** status always comes from the Jobs API (later, system.lakeflow tables), so
  there is nothing to reconcile. My requests reads the list from `request_status`.
- `tests/test_db.py` runs the migrations against a real Postgres when `PG_TEST_DSN` is set
  (CI starts one); locally without it, those tests are skipped and say so.
- **Before a pull request that changes `db/` or `store.py`, try it on a Lakebase dev branch**
  (never production): `python3 tests/dev_branch.py --profile <cli profile> --branch dev`. It
  installs from scratch in the branch's empty `databricks_postgres` database, round-trips
  requests and settings, then upgrades the branch's copy of production (the `self_service`
  database: the real data is there, not in `databricks_postgres`) and checks no request was
  lost. Your branch role needs `DATABRICKS_SUPERUSER` (Lakebase > the branch > Roles &
  Databases); a dev branch's data and schema are yours to change. The membership does not
  give CREATEROLE, so `test_db.py`'s role tests cannot run there; CI's Postgres runs them.

## Gotchas learned the hard way

- **Fixed paths before parameters:** FastAPI matches routes in order, so `/approvals/settings`
  and `/approvals/overview` are registered before `/approvals/{request_id}`.
- **Browsers keep old CSS and JS:** static links carry `?v=<hash of app.css and app.js>`
  (`asset_version`); keep it on any new static file a page links to.
- **A model's JSON is data:** filter what it returns, then cap the counts (`summary.parse`);
  capping first drops good items behind bad ones.
- **Every event type needs a label wherever events are shown** (`_components.html`
  `conversation`); a new type without one was a latent KeyError. Use `.get` with a default.
- **Local runs:** a uvicorn started with `--reload` leaves a reloader holding the port; run
  without it, and stop old ones before starting again.

## Operating it

- **Failures are never silent.** Where the app works around a failure (a fallback, an unknown
  answer), it logs a warning (`portal.warn`): read the app's Logs in the workspace. A quiet
  fallback once hid a database outage for hours.
- **`/healthz`** checks, as the app's own identity, that its database answers and its jobs are
  found (503 if not). After a deploy, open it: "deploy SUCCEEDED" only means the process started.
- **Minimum versions in `requirements.txt`.** Databricks Apps may have older packages installed,
  and an unpinned requirement accepts them (an old `databricks-sdk` without the Postgres API took
  both apps down). Raise a minimum when the code needs something newer.
- **Approvers see every BU for now** (`LakebaseStore.bus_for`); when BU data owners approve, map
  their groups to BUs there and filter.

## Run and test

```bash
pip install -r requirements.txt httpx
python3 -m unittest discover -s tests          # or ./scripts/test.sh app from the repository root
PORTAL_CONFIG=<config.json> PORTAL_USER=<email> python3 main.py   # locally, signed in with the Databricks CLI
```

To run locally against a real database, use the Lakebase **dev** branch (never production):
psycopg needs libpq (`brew install libpq`, then `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/opt/libpq/lib`),
`PGUSER=<your email>`, and a `database` entry in `config.json` with the dev branch's host and
endpoint. Your branch role needs `DATABRICKS_SUPERUSER` there. `APP_MODE=approvals` (or
`"mode": "approvals"` in `config.json`) runs the approvals app on the same database.

A local `config.json` has the same shape as the one the build writes
(`python3 scripts/app_build.py hub --outputs <json>`: `bundle/hub/build/self-service/config.json`). Running locally uses your
own identity, so it sees what you can see, not what the app's service principal can.

## Deploying

Through a merged pull request, like everything else. `scripts/app_deploy.py` deploys the hub
(`config/self-service/hub.yaml`: both apps, the database), then the two jobs in every
workspace the app serves (every workspace file without `self_service: false`), reading what
it needs about each from that workspace's Terraform output `self_service`. To see what a
deploy would change, signed in with the Databricks CLI: `python3 scripts/app_deploy.py --plan`
(it changes nothing). Check afterwards that each app's active deployment `SUCCEEDED`
(`databricks apps get <name>`). The app's logs need a user sign-in to read.

- **The bundles' state** is in the workspaces (`<admin_path>/bundle/hub`, `<admin_path>/bundle/jobs`),
  so any deploy, from CI or a laptop, sees the same state. Still, only CI deploys.
- **A new setting** goes in `config/self-service/app.yaml` (with its default), is read by
  `app_build.app_config()` into `config.json`, and, if a wrong value would fail later, is
  checked in `app_build.check()` with a test in `apps/self-service/tests/test_build.py`.
- **The apps' identities** (`app_ids` in `hub.yaml`) are set once, after the hub's first deploy
  creates the apps; the deploy prints them, and fails if they no longer match.

## Known limits

- My Requests shows a user's requests among each job's newest 200 runs (everyone's).
- The user's forwarded token is the hub's: another workspace's SCIM `/Me` may not accept it,
  so the team schema and folder forms may offer no groups there.
- In-memory caches are per app process; they reset on every deploy.
