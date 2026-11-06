---
name: support-a-temporary-schema
description: Use when someone asks about a temporary schema (cd_tmp_...): whose it is and when it is deleted, why it was deleted, extending it, a request to extend it that waits, why they cannot create another, how many each person may have or how long they last, or what the daily cleanup did. Reads the schema's tags and the cleanup's report; changes happen only in the app (extend), the admin app (approve, Settings) or a pull request.
---

# Support a temporary schema

**What they are:** each person's own short-term schema, `cd_tmp_<name>`, in their business unit's catalog. It is **deleted** (with everything in it) once its date has passed, by the daily **Temporary schema cleanup** job in the hub (06:00 UTC). Its tags say everything:

| Tag | Means |
| --- | --- |
| `cd_user` | Whose it is |
| `cd_schema_kind` = `temporary` | It will be deleted after its date |
| `cd_expires` | The date: deleted after it (still kept on the day itself) |
| `cd_created` | When it was made |
| `cd_pending_request` | An extension waits for an approver: **never deleted while it waits** |
| `cd_converted_from` = `personal` | It was a personal schema, made temporary |

Find them: Catalog Explorer in the person's workspace > the catalog > the schema > **Details**.

## What they ask, and what to do

| They ask | Do |
| --- | --- |
| "When is it deleted?" | Its `cd_expires`; also on the app's card (a bar: N of M days left) and the form |
| "Extend it" | The owner: in the app, the temporary schema > **Extend temporary schema** (7 days, with a reason). It waits for an approver; the schema is held meanwhile. An approver: the admin app > Pending Approvals > approve or reject (rejected: deleted at the next cleanup if its date has passed) |
| "Why was it deleted?" | The cleanup's run of that day (the hub > Jobs > Temporary schema cleanup > the run's output): it lists each deleted schema, whose, and how many tables. Nothing deletes one early |
| "Can I get it back?" | Not from the app. Within 7 days of the deletion a platform admin may recover managed tables (Unity Catalog `UNDROP`); after that, no |
| "I can't create another" | They are at the limit (the card: N of N used). Wait for one to expire, or extend or drop one |
| "Allow 2 per person" / "make them last 60 days" | The limit: the admin app > Settings > **Schemas** (no pull request). The days: `jobs.temporary_schema.days` in `config/self-service/app.yaml` (the skill **update-self-service-app**, then **pull-request-from-databricks**) |
| "What would the cleanup delete tomorrow?" | A workspace admin: the hub > Jobs > Temporary schema cleanup > **Run now with different parameters**, `dry_run` = `true`: it reports, deletes nothing |
| "Keep it as a project schema" | Not offered for now: they request a project schema and copy what they need into it |

## Never

- Never change a schema's tags or rights by hand to "extend" it: an extension is a request an approver decides, so it is recorded.
- Never run the cleanup without `dry_run` by hand.
