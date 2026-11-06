# Databricks notebook source
# MAGIC %md
# MAGIC # Temporary schema cleanup
# MAGIC Drops the temporary schemas whose `cd_expires` date has passed (`DROP SCHEMA ... CASCADE`: the
# MAGIC schema and everything in it), and reports every temporary schema it looked at: dropped, kept
# MAGIC (not expired yet) or failed, with who it was for, when it was created and when it expires. Its
# MAGIC summary leads: how many schemas it deleted, whose (by email) and how many tables each held.
# MAGIC Run once a day by the hub's `Temporary schema cleanup` job, over every served workspace's catalog
# MAGIC (written in at build: one job for all of them). A schema counts only when the
# MAGIC self-service job made it as a temporary one: tagged `cd_managed_by=self_service` and
# MAGIC `cd_schema_kind=temporary`, and named `<prefix>tmp_<name>` (or an old personal schema it made
# MAGIC temporary). Personal schemas are not offered any more: each one left is made temporary first
# MAGIC (its owner's rights narrowed to `temporary_privileges`, `cd_expires` `temporary_days` ahead,
# MAGIC `cd_converted_from=personal`), so it expires like the others. One with a request waiting for an
# MAGIC approver (more time: tag `cd_pending_request`) is never deleted until it is decided.
# MAGIC Parameter: `dry_run` ("true": report
# MAGIC what it would drop, drop nothing). Edit this notebook in the repository
# MAGIC (bundle/jobs/notebooks/temporary_cleanup.py): the next deploy replaces it.

# COMMAND ----------

import datetime
import json
import re

# Written here by scripts/app_build.py from config/self-service/app.yaml and the workspace's
# Terraform output: change them there. A run cannot change them.
prefix = ${jsonencode(prefix)}
catalogs = ${jsonencode(allowed_catalogs)}
temporary_days = ${jsonencode(temporary_days)}             # an old personal schema expires this many days after it is made temporary
temporary_privileges = ${jsonencode(temporary_privileges)}   # ... and its owner keeps only these: use it, never share it

dbutils.widgets.text("dry_run", "")
dry_run = dbutils.widgets.get("dry_run").strip().lower() == "true"
today = datetime.date.today()
if not all(re.fullmatch(r"[A-Za-z0-9_-]+", c) for c in catalogs) or not re.fullmatch(r"[a-z0-9_]+", prefix):
    raise ValueError(f"not catalogs or a prefix: {catalogs}, {prefix!r}")
if not all(re.fullmatch(r"[A-Z_]+", p) for p in temporary_privileges) or {"MANAGE", "ALL_PRIVILEGES"} & set(temporary_privileges):
    raise ValueError(f"not a temporary schema's privileges: {temporary_privileges}")
email = r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]+"

# COMMAND ----------

# Every temporary schema, with the tags that say whose it is and until when; first, every old
# personal schema made temporary (once: then it is a temporary one).
report, converted = [], []
until = (today + datetime.timedelta(days=temporary_days)).isoformat()
for catalog in catalogs:
    tags = {}
    for r in spark.sql(f"SELECT schema_name, tag_name, tag_value FROM `{catalog}`.information_schema.schema_tags "
                       "WHERE tag_name IN ('cd_managed_by', 'cd_schema_kind', 'cd_user', 'cd_created', 'cd_expires', "
                       "'cd_converted_from', 'cd_pending_request')").collect():
        tags.setdefault(r.schema_name, {})[r.tag_name] = r.tag_value
    for schema, t in sorted(tags.items()):
        if t.get("cd_schema_kind") != "personal" or t.get("cd_managed_by") != "self_service":
            continue
        row = {"catalog": catalog, "schema": schema, "user": t.get("cd_user", ""), "expires": until, "why": ""}
        converted.append(row)
        if not re.fullmatch(r"[a-z0-9_]+", schema) or not re.fullmatch(email, row["user"]):
            row["why"] = "kept as it is: an unexpected name or owner"
            continue
        if dry_run:
            row["why"] = "would be made temporary (dry run)"
            continue
        name = f"`{catalog}`.`{schema}`"
        try:   # their new rights first, then the old ones go: they never lose access in between
            spark.sql(f"GRANT {', '.join(p.replace('_', ' ') for p in temporary_privileges)} ON SCHEMA {name} TO `{row['user']}`")
            spark.sql(f"REVOKE ALL PRIVILEGES, MANAGE ON SCHEMA {name} FROM `{row['user']}`")
            spark.sql(f"ALTER SCHEMA {name} SET TAGS ('cd_schema_kind' = 'temporary', 'cd_expires' = '{until}', "
                      "'cd_converted_from' = 'personal')")
            row["why"] = f"made temporary: deleted on {until} unless more time is approved, or it is kept"
            t.update(cd_schema_kind="temporary", cd_expires=until, cd_converted_from="personal")
        except Exception as e:
            row["why"] = "failed: " + str(e).splitlines()[0][:300]
    for schema, t in sorted(tags.items()):
        if t.get("cd_schema_kind") != "temporary" or t.get("cd_managed_by") != "self_service":
            continue   # not a temporary schema the self-service job made: never touched
        row = {"catalog": catalog, "schema": schema, "user": t.get("cd_user", ""), "created": t.get("cd_created", ""),
               "expires": t.get("cd_expires", ""), "tables": None, "action": "kept", "why": ""}
        report.append(row)
        if not re.fullmatch(f"{prefix}tmp_[a-z0-9_]+", schema) and t.get("cd_converted_from") != "personal":
            row["why"] = f"not named {prefix}tmp_<name>"
            continue
        try:
            expires = datetime.date.fromisoformat(row["expires"])
        except ValueError:
            row["why"] = "no valid cd_expires date"
            continue
        row["tables"] = spark.sql(f"SELECT count(*) AS n FROM `{catalog}`.information_schema.tables "
                                  f"WHERE table_schema = '{schema}'").first().n
        if expires >= today:
            row["why"] = f"expires on {row['expires']}"
            continue
        if t.get("cd_pending_request"):   # more time, or keeping it, waits for an approver: never deleted until decided
            row["why"] = f"expired on {row['expires']}, but {t['cd_pending_request']} waits for an approver"
            continue
        if dry_run:
            row["action"], row["why"] = "would drop", f"expired on {row['expires']} (dry run)"
            continue
        try:
            spark.sql(f"DROP SCHEMA `{catalog}`.`{schema}` CASCADE")
            row["action"], row["why"] = "dropped", f"expired on {row['expires']}"
        except Exception as e:   # reported, and the run fails below, after every schema was looked at
            row["action"], row["why"] = "failed", str(e).splitlines()[0][:300]

# COMMAND ----------

# The day's report: the summary (how many deleted, whose, and how many tables each), a line per
# temporary schema and a table to read in the run's output, and the same as JSON (the run's result,
# and task value report). Written from the report itself, so every number and email is exact.
counts = {a: sum(1 for r in report if r["action"] == a) for a in ("dropped", "would drop", "kept", "failed")}
gone = [r for r in report if r["action"] in ("dropped", "would drop")]
plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
verb = "would delete" if dry_run else "deleted"
summary = [f"Temporary schema cleanup on {today.isoformat()}{' (dry run)' if dry_run else ''}: {verb} "
           f"{plural(len(gone), 'schema')}, with {plural(sum(r['tables'] or 0 for r in gone), 'table')}."]
summary += [f"  {r['user'] or 'unknown owner'}: {r['catalog']}.{r['schema']} ({plural(r['tables'] or 0, 'table')})" for r in gone]
if counts["failed"]:
    summary += [f"Could not delete {plural(counts['failed'], 'schema')}:"]
    summary += [f"  {r['user'] or 'unknown owner'}: {r['catalog']}.{r['schema']}: {r['why']}" for r in report if r["action"] == "failed"]
summary += [f"Kept {plural(counts['kept'], 'temporary schema')} that {'has' if counts['kept'] == 1 else 'have'} not expired."]
made = [r for r in converted if r["why"].startswith(("made temporary", "would be made"))]
failed_to_convert = [r for r in converted if r["why"].startswith("failed")]
if made:
    summary += [f"{'Would make' if dry_run else 'Made'} {plural(len(made), 'personal schema')} temporary, to be deleted on {until} "
                "unless more time is approved or they are kept:"]
    summary += [f"  {r['user']}: {r['catalog']}.{r['schema']}" for r in made]
if failed_to_convert:
    summary += [f"Could not make {plural(len(failed_to_convert), 'personal schema')} temporary:"]
    summary += [f"  {r['user'] or 'unknown owner'}: {r['catalog']}.{r['schema']}: {r['why']}" for r in failed_to_convert]
summary = "\n".join(summary)
lines = [f"{r['action']}: {r['catalog']}.{r['schema']}, for {r['user'] or 'an unknown owner'}, created {r['created'] or 'on an unknown date'}, "
         f"expires {r['expires'] or 'never (no date)'}, {r['tables'] if r['tables'] is not None else 'an unknown number of'} tables. {r['why']}"
         for r in report]
print(summary, "", *lines, sep="\n")
if report:
    display(spark.createDataFrame([{**r, "tables": -1 if r["tables"] is None else r["tables"]} for r in report]))
result = json.dumps({"date": today.isoformat(), "dry_run": dry_run, "counts": counts, "summary": summary, "schemas": report,
                     "converted": converted})
dbutils.jobs.taskValues.set("report", result)
if counts["failed"] or failed_to_convert:
    raise RuntimeError(f"{counts['failed']} temporary schema(s) could not be dropped and {len(failed_to_convert)} personal "
                       "schema(s) could not be made temporary: see the report above.")
dbutils.notebook.exit(result)
