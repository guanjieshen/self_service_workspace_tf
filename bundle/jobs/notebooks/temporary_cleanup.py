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
# MAGIC `cd_schema_kind=temporary`, and named `<prefix>tmp_<name>`. Parameter: `dry_run` ("true": report
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

dbutils.widgets.text("dry_run", "")
dry_run = dbutils.widgets.get("dry_run").strip().lower() == "true"
today = datetime.date.today()
if not all(re.fullmatch(r"[A-Za-z0-9_-]+", c) for c in catalogs) or not re.fullmatch(r"[a-z0-9_]+", prefix):
    raise ValueError(f"not catalogs or a prefix: {catalogs}, {prefix!r}")

# COMMAND ----------

# Every temporary schema, with the tags that say whose it is and until when.
report = []
for catalog in catalogs:
    tags = {}
    for r in spark.sql(f"SELECT schema_name, tag_name, tag_value FROM `{catalog}`.information_schema.schema_tags "
                       "WHERE tag_name IN ('cd_managed_by', 'cd_schema_kind', 'cd_user', 'cd_created', 'cd_expires')").collect():
        tags.setdefault(r.schema_name, {})[r.tag_name] = r.tag_value
    for schema, t in sorted(tags.items()):
        if t.get("cd_schema_kind") != "temporary" or t.get("cd_managed_by") != "self_service":
            continue   # not a temporary schema the self-service job made: never touched
        row = {"catalog": catalog, "schema": schema, "user": t.get("cd_user", ""), "created": t.get("cd_created", ""),
               "expires": t.get("cd_expires", ""), "tables": None, "action": "kept", "why": ""}
        report.append(row)
        if not re.fullmatch(f"{prefix}tmp_[a-z0-9_]+", schema):
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
summary = "\n".join(summary)
lines = [f"{r['action']}: {r['catalog']}.{r['schema']}, for {r['user'] or 'an unknown owner'}, created {r['created'] or 'on an unknown date'}, "
         f"expires {r['expires'] or 'never (no date)'}, {r['tables'] if r['tables'] is not None else 'an unknown number of'} tables. {r['why']}"
         for r in report]
print(summary, "", *lines, sep="\n")
if report:
    display(spark.createDataFrame([{**r, "tables": -1 if r["tables"] is None else r["tables"]} for r in report]))
result = json.dumps({"date": today.isoformat(), "dry_run": dry_run, "counts": counts, "summary": summary, "schemas": report})
dbutils.jobs.taskValues.set("report", result)
if counts["failed"]:
    raise RuntimeError(f"{counts['failed']} temporary schema(s) could not be dropped: see the report above.")
dbutils.notebook.exit(result)
