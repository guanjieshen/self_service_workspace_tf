---
name: support-a-temporary-schema
description: Use when someone asks about a temporary schema (cd_tmp_...), such as whose it is and when it is deleted, why it was deleted, extending it, a request to extend it that waits, why they cannot create another, how many each person may have or how long they last, or what the daily cleanup did. Reads the schema's tags and the cleanup's report; changes happen only in the app (extend), the admin app (approve, Settings) or a pull request.
---

# Support a temporary schema

**What they are:** each person's own short-term schema, `cd_tmp_<name>`, in their business unit's catalog. It is **deleted** (with everything in it) once its date has passed, by the daily **Temporary schema cleanup** job in the hub (06:00 UTC). Its tags say everything:

| Tag | Means |
| --- | --- |
| `cd_user` | Whose it is |
| `cd_schema_kind` = `temporary` | It will be deleted after its date |
| `cd_expires` | The date: deleted after it (still kept on the day itself) |
| `cd_created` | When it was made |
| `cd_pending_request` | An extension waits for an approver (only when `human_approval` lists `temporary_extension`): **never deleted while it waits** |
| `cd_converted_from` = `personal` | It was a personal schema, made temporary |

Find them: Catalog Explorer in the person's workspace > the catalog > the schema > **Details**.

## What they ask, and what to do

| They ask | Do |
| --- | --- |
| "When is it deleted?" | At the daily cleanup after its `cd_expires` date (06:00 UTC the next morning); the app's card shows that time ("Expires", in their time zone) and the days remaining |
| "Extend it" | The owner: in the app, the temporary schema > **Extend schema** (30 days, with a reason), from either of their accounts. Or an approver for them: the admin app > **Temporary schemas** > **Extend 30 days**. It is added straight away, as often as they ask. Only if `human_approval` lists `temporary_extension` does it wait for an approver (the schema is held meanwhile): the admin app > Pending Approvals > approve or reject |
| "Why was it deleted?" | The cleanup's run of that day (the hub > Jobs > Temporary schema cleanup > the run's output): it lists each deleted schema, whose, and how many tables. Or its owner or an approver deleted it early in the app (a **Schema deleted** request in My requests or the admin app's All requests) |
| "I lost access to it" (they removed their own permissions) | The owner: the temporary schema > **Restore permissions**; or an approver: the admin app > **Temporary schemas** > **Restore permissions**. It gives back the grants it had when it was made |
| "Delete it now" | The owner: the temporary schema > **Delete** (type its name); or an approver: the admin app > **Temporary schemas** > **Delete**. Everything in it is gone for good |
| "Can I get it back?" | Not from the app. Within 7 days of the deletion a platform admin may recover managed tables (Unity Catalog `UNDROP`); after that, no |
| "I can't create another" | They are at the limit (the card: N of N used). Wait for one to expire, or extend or drop one |
| "Allow 2 per person" / "make them last 60 days" | The limit: the admin app > Settings > **Schemas** (no pull request). The days: `jobs.temporary_schema.days` in `config/self-service/app.yaml` (the skill **update-self-service-app**, then **pull-request-from-databricks**) |
| "What would the cleanup delete tomorrow?" | A workspace admin: the hub > Jobs > Temporary schema cleanup > **Run now with different parameters**, `dry_run` = `true`: it reports, deletes nothing |
| "Keep it as a project schema" | Not offered for now: they request a project schema and copy what they need into it |

## Never

- Never change a schema's tags or rights by hand to "extend" it: an extension is a request, so it is recorded.
- Never run the cleanup without `dry_run` by hand.
