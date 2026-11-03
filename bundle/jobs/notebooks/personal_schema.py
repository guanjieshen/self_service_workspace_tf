# Databricks notebook source
# MAGIC %md
# MAGIC # Personal, project or team schema
# MAGIC Creates a schema for one user, grants it to them (all privileges and MANAGE, so they can share
# MAGIC it themselves), and to their group for a team schema, and tags it for self-service tracking.
# MAGIC Run by the `<BU> personal schema` job when the self-service app asks; safe to run again.
# MAGIC Parameters: `user` (email), `catalog` (required, one of the allowed catalogs), `schema`
# MAGIC (empty = their personal schema, `cd_<email before @>`; a name = a project or team schema,
# MAGIC which may not start with the personal prefix), `owner_group` (optional, a team schema: a group
# MAGIC the user belongs to, which gets the same rights), `reason` (why they need it; kept with the run) and
# MAGIC `request_id` (optional). Edit this notebook
# MAGIC in the repository (bundle/jobs/notebooks/personal_schema.py): the next deploy replaces it.

# COMMAND ----------

import datetime
import json
import re

from databricks.sdk import WorkspaceClient

# Written here by scripts/app_build.py from config/self-service/app.yaml and the workspace's
# Terraform output: change them there. A run cannot change them.
prefix = ${jsonencode(prefix)}
privileges = ${jsonencode(privileges)}
owner = ${jsonencode(owner)}
allowed_catalogs = ${jsonencode(allowed_catalogs)}
# The request record check (below): the app's records, this workspace's name in them, and
# the kinds that always need an approver. requests_catalog empty = off.
requests_catalog = ${jsonencode(requests_catalog)}
workspace_name = ${jsonencode(workspace_name)}
human_approval = ${jsonencode(human_approval)}

# COMMAND ----------

${request_record_check}

# COMMAND ----------

# The request.
for name in ("user", "schema", "catalog", "owner_group", "reason", "request_id"):
    dbutils.widgets.text(name, "")
user = dbutils.widgets.get("user").strip().lower()
schema = dbutils.widgets.get("schema").strip().lower()
catalog = dbutils.widgets.get("catalog").strip()
owner_group = dbutils.widgets.get("owner_group").strip()
reason = dbutils.widgets.get("reason").strip()   # why they need it: kept with the run, never used in a query
request_id = dbutils.widgets.get("request_id").strip()
personal = prefix + re.sub(r"[^a-z0-9]+", "_", user.split("@")[0]).strip("_")
kind = "personal" if not schema or schema == personal else "team" if owner_group else "project"
schema = schema or personal

# COMMAND ----------

# Check the request (the app checks it too). Everything below goes into SQL.
if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]+", user):
    raise ValueError(f"user must be an email address, not {user!r}")
if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", schema):
    raise ValueError(f"schema must be lowercase letters, digits and _, not {schema!r}")
if kind != "personal" and schema.startswith(prefix):
    raise ValueError(f"a project or team schema may not start with {prefix} (personal schemas are named {prefix}<name>)")
if owner_group and kind == "personal":
    raise ValueError("a personal schema is the user's alone: owner_group is for a team schema")
if owner_group and not re.fullmatch(r"[A-Za-z0-9 _.-]+", owner_group):
    raise ValueError(f"not a group name: {owner_group!r}")
if catalog not in allowed_catalogs:
    raise ValueError(f"catalog must be one of {', '.join(allowed_catalogs)}, not {catalog!r}")
if len(reason) > 1000:
    raise ValueError(f"reason is at most 1000 characters, not {len(reason)}")
if not re.fullmatch(r"[A-Za-z0-9._:/-]{0,100}", request_id):
    raise ValueError(f"request_id may only contain letters, digits and . _ : / -, not {request_id!r}")
if not all(re.fullmatch(r"[A-Z_]+", p) for p in privileges):
    raise ValueError(f"not privileges: {privileges}")

# A team schema's group must be one of the user's own (the app checks it too).
if owner_group:
    me = list(WorkspaceClient().users.list(filter=f'userName eq "{user}"', attributes="id,userName,groups"))
    if not me or owner_group not in {g.display for g in me[0].groups or []}:
        raise ValueError(f"{user} is not in the group {owner_group}")

# Only a request the app recorded, for these parameters (off unless jobs.require_request_record).
check_request_record(request_id, {"kind": f"{kind}_schema", "workspace": workspace_name, "requested_by": user,
                                  "name": schema, "owner_group": owner_group})

# An existing schema must already be this user's: never hand over another person's or a shared one.
exists = spark.sql(f"SELECT 1 FROM `{catalog}`.information_schema.schemata WHERE schema_name = '{schema}'").count() > 0
tagged = spark.sql(f"SELECT tag_value FROM `{catalog}`.information_schema.schema_tags "
                   f"WHERE schema_name = '{schema}' AND tag_name = 'cd_user'").collect()
if exists and [r.tag_value for r in tagged] != [user]:
    raise ValueError(f"{catalog}.{schema} already exists and is not {user}'s")

# COMMAND ----------

# Create and tag first (so a failed run can be run again), then grant and hand it to the owner.
name = f"`{catalog}`.`{schema}`"
tags = {"cd_managed_by": "self_service", "cd_user": user, "cd_schema_kind": kind}
if not exists:
    tags["cd_created"] = datetime.date.today().isoformat()
if request_id:
    tags["cd_request_id"] = request_id

# A new schema is created on its own (no IF NOT EXISTS): when two requests for the same name run
# at once, both see it missing, and only the first may create it; the other stops here, so it is
# never handed to two people. An existing one (checked above: this user's) is a run again.
if not exists:
    try:
        spark.sql(f"CREATE SCHEMA {name} COMMENT '{kind.capitalize()} schema of {owner_group or user} (self-service)'")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "already exists" in str(e):
            raise ValueError(f"{catalog}.{schema} was just created by another request: choose another name") from e
        raise
spark.sql(f"ALTER SCHEMA {name} SET TAGS ({', '.join(f'{k!r} = {v!r}' for k, v in tags.items())})")
grant = ', '.join(p.replace('_', ' ') for p in privileges)
spark.sql(f"GRANT {grant} ON SCHEMA {name} TO `{user}`")
if owner_group:
    try:
        spark.sql(f"GRANT {grant} ON SCHEMA {name} TO `{owner_group}`")
    except Exception as e:   # the schema stays the user's; asking again with another group is safe
        raise ValueError(f"{owner_group} cannot be given the schema: Unity Catalog grants only to account groups "
                         f"(synced from Entra ID), not to groups that exist only in the workspace") from e
    spark.sql(f"ALTER SCHEMA {name} SET TAGS ('cd_owner_group' = {owner_group!r})")
if owner:
    spark.sql(f"ALTER SCHEMA {name} OWNER TO `{owner}`")

dbutils.notebook.exit(json.dumps({"catalog": catalog, "schema": schema, "kind": kind, "user": user, "owner_group": owner_group, "reason": reason, "created": not exists}))
