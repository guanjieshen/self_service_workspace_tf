---
name: change-the-database
description: Use when a change needs the apps to store something new or differently in their database (a new field on a request, a new table, a new kind of request, a new allowed value). Writes a database migration, its grants, the code in store.py and its tests, tries it on a Lakebase branch, then opens the pull request. Also when someone asks how the database is changed safely or how to get data back. Follows agents/database.md; refuses anything that could lose data.
---

# Change the database

The person may not know what a database migration is. Read **`agents/database.md`** first (it is written for someone new to Lakebase) and follow it; explain each step in one plain sentence.

## 1. Agree what changes

In plain words: what new thing is stored, for what, and whether anything existing changes. If anything would be **removed or renamed**, stop: that is a later, separate step (add, then use; remove only in a later release). Say so.

## 2. Make the change (agents/database.md, section 4)

1. A **new migration**, the next number in `apps/self-service/db/migrations/`, starting with a comment saying what and why. **Never edit one that has run** (any on `main`).
2. **Add, never rename or drop:** a new column is nullable or has a default; a changed `CHECK` keeps every value it allowed before.
3. **Rights:** a new table's `GRANT SELECT, INSERT ...` in `apps/self-service/db/grants.sql`. Never `UPDATE` or `DELETE`.
4. **The code:** the query in `apps/self-service/store.py`.
5. **The tests:** the migration's name in `test_migrations_run_once`, and a round trip in `apps/self-service/tests/test_db.py`.
6. **Guides and changelog:** `agents/database.md` (section 2's table, if a table changed), `agents/app.md`, and `CHANGELOG.md` under **Unreleased** (what the deploy runs: "migration `009_...`").

## 3. Try it on a branch (agents/database.md, section 5)

A Lakebase branch is a copy of production, made in seconds, where nothing can harm the real data. Create one (`dev`, 7 days), give yourself `DATABRICKS_SUPERUSER` **on that branch only**, run `apps/self-service/tests/dev_branch.py` against it, and say what it printed. Delete the branch afterwards.

## 4. The pull request

The skill **pull-request-from-databricks**. In the description: what the migration changes, and that it was tried on a branch. The **Database tests** check must be green.

## Never

- Never change production by hand (no SQL editor on production), never edit a migration that ran, never drop data without a `-- destructive: <why>` line a reviewer has agreed to, never remove `prevent_destroy`.
- To get data back after a mistake: `agents/database.md`, section 6 (a branch from a point in time, within 7 days), with a platform admin.
