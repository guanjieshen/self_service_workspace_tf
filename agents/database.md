# The apps' database (Lakebase): what it is, how to change it, how not to lose data

> **Start here** if a change touches `apps/self-service/db/`, `apps/self-service/store.py`, or anything
> the apps keep about a request. You need no database background: this page says what each piece is,
> what to do, in order, and what never to do.

## 1. What it is, in plain words

| Word | What it means here |
| --- | --- |
| **Lakebase** | Databricks' managed **Postgres** database service. Postgres is a standard SQL database: tables, rows, SQL. Databricks runs it for us (no servers to look after). |
| **Project** | One Lakebase database service. Ours is **`cd-self-service`** (`database.project_id` in `config/self-service/app.yaml`), in the hub workspace. |
| **Branch** | A full copy of the database, made **instantly** (it shares the unchanged data underneath, so it costs almost nothing). **`production`** is the real one the apps use. Any other branch is a safe sandbox: change it, break it, delete it; production does not notice. |
| **Endpoint** | The address (host) the apps connect to; each branch has one (`.../endpoints/primary`). It scales to zero when idle (`suspend_after`) and wakes on the next connection. |
| **Database** | Inside a branch, the named database **`self_service`** holds our tables. |
| **History (point in time)** | Lakebase keeps every change for **7 days** (the project's `history_retention_duration`, 604800s). You can make a branch **as the database was at any moment in that week**: this is how a mistake is undone. |
| **Migration** | A numbered `.sql` file in `apps/self-service/db/migrations/` that changes the tables (adds a column, a table, a view). Each runs **once**, in order, recorded in the table `self_service.schema_migrations`. |
| **Role** | A database login. Each app has one (its service principal), the deploying identity owns the database, and `database.readers` (emails in `hub.yaml`) may read it. |

## 2. What the database holds, and what it does not

Only what the apps create and **no other system keeps** (`agents/app.md`, "The database"):

| Table | Holds |
| --- | --- |
| `requests` | One row per request: kind, workspace, business unit, who, the name, the team group, the reason, the days (an extension) |
| `request_events` | Every step of a request, in order: submitted, AI summary, questions, replies, comments, approved or rejected, its job run, a failure to start |
| `setting_events` | Every change made in the admin app's Settings (who, when, old and new) |
| `business_unit_choices` | The business unit each person chose (only without a directory lookup) |
| `guided_tours` | Who has had the Genie One guided tour |

Views (computed, nothing stored): `request_status`, `settings`, `chosen_business_units`.
**Not here, read from the source:** a run's status (Jobs API), schemas and their tags (Unity
Catalog), groups (Entra ID), the cleanup's reports (its job run).

**The tables are append-only:** the apps may only `INSERT` and `SELECT`, never `UPDATE` or
`DELETE` (`db/grants.sql`). A request's state is its latest event, never a column that changes. So
an app bug can add a wrong row, but cannot erase history.

## 3. How a change reaches production (no one runs anything by hand)

On every merge to `main`, **Deploy the app** (`scripts/app_deploy.py`) does, in this order:

| # | Step | Where |
| --- | --- | --- |
| 1 | Make sure the project exists, and the database `self_service` and the readers' roles | `ensure_database` in `scripts/app_deploy.py` |
| 2 | Run every migration not yet run, each in its own transaction, then `grants.sql` (every time) | `apps/self-service/db/migrate.py` |
| 3 | Deploy the bundle, then each app's **new code** | `bundle/hub/` |

Migrations run **before** the new code starts, so new code never meets an old database. But the
**old code keeps running** while the migration runs, so every migration must work with the
version already running (below). The deploy's log says `migrations applied: 008_...`.

The project is protected: `lifecycle.prevent_destroy: true` in `bundle/hub/resources/apps.yml`
stops the bundle from ever deleting it. Never remove that line.

## 4. Making a database change, step by step

| # | Do | Why |
| --- | --- | --- |
| 1 | **Write a new migration**, the next number: `apps/self-service/db/migrations/009_what_it_does.sql`. Start it with a comment saying what and why. | Each runs once, in number order |
| 2 | **Never edit a migration that has run** (any that is on `main`). To change it, add another. | Production has run the old text; an edit never reaches it, and a fresh install would differ |
| 3 | **Add, then use; never rename or drop in one step.** Add a column (`ADD COLUMN ... ` nullable, or with a default) in one release; start using it in the code; only later, in another release, remove what is no longer used. | The running app must still work with the new tables during the deploy |
| 4 | A view that lists columns with `*`: recreate it with the columns **named**, new ones **last** (`CREATE OR REPLACE VIEW`; see `008`). | Postgres refuses a replaced view whose columns move |
| 5 | A change to a `CHECK` (an allowed list, such as the kinds of request): drop it and add it again **with every value it allowed before**, plus the new ones. | Old rows must still pass |
| 6 | Anything with `DROP`, `TRUNCATE` or `DELETE` needs a line `-- destructive: <why it is safe>`; the tests fail without it, and the reviewer must read it on purpose. | Data loss is never an accident |
| 7 | **The apps' rights:** a new table needs its `GRANT SELECT, INSERT ... TO {self_service}` (and `{approvals}`, `{readers}` as needed) in `db/grants.sql`. Never grant `UPDATE` or `DELETE`. | Append-only (section 2) |
| 8 | **The code:** every query is in `apps/self-service/store.py` (and only there). Add the new column to the `SELECT` and to what it returns. | One place to read |
| 9 | **The tests:** add the migration's name to `test_migrations_run_once` in `apps/self-service/tests/test_db.py`, and a round trip of the new column or table (`test_the_apps_store_round_trip_as_the_apps_role`). They run on a real Postgres in CI (**Database tests**). | A migration that fails here would fail the deploy |
| 10 | **Try it on a Lakebase branch** (section 5), then open the pull request. Say in it what the migration changes and that it was tried on a branch. | CI's Postgres is empty; a branch has the real data |

## 5. Trying a change safely on a branch (a copy of production)

A branch is the way to try a migration **against the real data** with no risk to it.

| # | Do | How |
| --- | --- | --- |
| 1 | **Make a branch from production**, named `dev`, that expires on its own | Databricks: **Lakebase** (or Compute > Lakebase) > the project `cd-self-service` > **Branches** > **Create branch**, parent `production`, expiry 7 days. Or: `databricks postgres create-branch projects/cd-self-service dev --ttl 7d` (it copies production now; nothing is written to production) |
| 2 | **Give yourself the right to change it** | The branch > **Roles & Databases** > your role > `DATABRICKS_SUPERUSER` (on the dev branch only, never on production) |
| 3 | **Run the check** | From the repository, signed in with the Databricks CLI: `python3 apps/self-service/tests/dev_branch.py --profile <your profile> --project cd-self-service --branch dev`. It installs from scratch in the branch's empty database and runs every migration twice (the second time nothing must run), then **upgrades the branch's copy of production** and checks **no request was lost**. It refuses `--branch production`. |
| 4 | **Look at the data** if you want | The branch > **SQL editor** (or Tables): `SELECT * FROM self_service.request_status ORDER BY created_at DESC LIMIT 20;` |
| 5 | **Delete the branch** when done (or let it expire) | Branches > the branch > Delete. Production is untouched either way. |

A branch's data and tables are yours to change. Production's are never changed by hand.

## 6. If something went wrong: getting data back

Because the tables are append-only and Lakebase keeps **7 days of history**, almost nothing is
lost for good. Act **within the 7 days**.

| What happened | What to do |
| --- | --- |
| A deploy's migration failed | Nothing changed: each migration is one transaction, and the deploy stops before the new code. Fix the migration in a pull request (it never ran, so editing it is fine), merge again. |
| A migration ran and did the wrong thing (a wrong column, a wrong view) | Add the next migration that puts it right, as any change (section 4). Do not edit the one that ran. |
| Rows were lost or damaged (a destructive migration, a hand edit) | 1. **Make a branch from production as it was before** (Lakebase > the project > Branches > Create branch > parent `production`, **from a point in time** just before the mistake; the time is in the deploy run's log, or the request's history). 2. Compare the two (SQL editor on each). 3. Copy the missing rows back into production with an `INSERT ... SELECT`, in a pull request reviewed like a migration (a migration file with `-- destructive:` if it changes anything), never typed into production. Ask a platform admin first. |
| The whole project was deleted | Lakebase keeps a deleted project for 7 days: `databricks postgres undelete-project projects/cd-self-service` (an account or workspace admin). The bundle refuses to delete it (`prevent_destroy`), so this needs someone deleting it by hand. |
| The app says "Your business unit can't be read just now" or requests cannot be recorded | The database is down or waking up (it scales to zero): wait a minute. The app's `/healthz` page says whether it can reach it. If it persists, look at the project in Lakebase (its state, its endpoint). |

## 7. Never

- **Never change production by hand** (SQL editor on production, `UPDATE`, `DELETE`). Every change
  is a migration in a pull request.
- **Never edit a migration that has run**, rename one, or reuse its number.
- **Never grant the apps `UPDATE` or `DELETE`**, or give `DATABRICKS_SUPERUSER` on production.
- **Never remove `prevent_destroy`** from `bundle/hub/resources/apps.yml`, or change
  `database.project_id` (it would make a new, empty database).
- **Never run `dev_branch.py` against production** (it refuses; do not work around it).
- **Never put a password or token anywhere:** every connection signs in with a short-lived
  Lakebase credential made at that moment (`store.py`, `migrate.py`, `dev_branch.py`).

## 8. Where everything is

| What | Where |
| --- | --- |
| The project (size, scale to zero, protection) | `bundle/hub/resources/apps.yml` (`postgres_projects`), sizes in `config/self-service/app.yaml` (`database:`) |
| Who may read the data | `config/self-service/hub.yaml`, `database.readers` (emails) |
| Creating the database and the readers' roles, running the migrations | `scripts/app_deploy.py` (`ensure_database`), `apps/self-service/db/migrate.py` |
| The migrations, the rights | `apps/self-service/db/migrations/NNN_*.sql`, `apps/self-service/db/grants.sql` |
| Every query | `apps/self-service/store.py` (the self-service app), `apps/self-service/approvals_store.py` (the admin app, through `store.py`) |
| The tests | `apps/self-service/tests/test_db.py` (rules always; a real Postgres with `PG_TEST_DSN`, as CI's **Database tests** job), `apps/self-service/tests/dev_branch.py` (a Lakebase branch, by hand) |
