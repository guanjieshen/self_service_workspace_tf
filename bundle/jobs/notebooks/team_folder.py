# Databricks notebook source
# MAGIC %md
# MAGIC # Workspace folder
# MAGIC Creates `/Workspace/<folder>` and gives the person who asked Can manage, and the group they
# MAGIC chose too, if any. Run by the `<BU> team folder` job when the self-service app asks. A folder at
# MAGIC the top of the workspace inherits only admins; the owners share it further with its Share button.
# MAGIC
# MAGIC Parameters: `folder` (lowercase letters, digits, dashes), `requested_by` (email), `owner_group`
# MAGIC (optional: a group the requester belongs to), `reason` (why they need it; kept with the run)
# MAGIC and `request_id` (optional). Edit this notebook in
# MAGIC the repository (bundle/jobs/notebooks/team_folder.py): the next deploy replaces it.

# COMMAND ----------

import json
import re

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

# Written here by scripts/app_build.py from config/self-service/app.yaml: change it there. A run cannot change it.
root = ${jsonencode(root)}
# The workspace's platform admins (its Terraform output): they can manage every folder, so a
# folder is never orphaned when its people move on.
admin_groups = ${jsonencode(admin_groups)}
# The request record check (below): the app's records, this workspace's name in them, and
# the kinds that always need an approver. requests_catalog empty = off.
requests_catalog = ${jsonencode(requests_catalog)}
workspace_name = ${jsonencode(workspace_name)}
human_approval = ${jsonencode(human_approval)}

# COMMAND ----------

${request_record_check}

# COMMAND ----------

# The request.
for name in ("folder", "requested_by", "owner_group", "reason", "request_id"):
    dbutils.widgets.text(name, "")
folder = dbutils.widgets.get("folder").strip()
requested_by = dbutils.widgets.get("requested_by").strip().lower()
owner_group = dbutils.widgets.get("owner_group").strip()
reason = dbutils.widgets.get("reason").strip()   # why they need it: kept with the run, never used in a query
request_id = dbutils.widgets.get("request_id").strip()

# COMMAND ----------

# Check the request (the app checks it too). Names go into SCIM filters, so only these characters get through.
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", folder) or folder in ("users", "shared", "repos", "admin", "workspace"):
    raise ValueError(f"folder must be lowercase letters, digits and dashes, and not a workspace folder: {folder!r}")
if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]+", requested_by):
    raise ValueError(f"requested_by must be an email address, not {requested_by!r}")
if owner_group and not re.fullmatch(r"[A-Za-z0-9 _.-]+", owner_group):
    raise ValueError(f"not a group name: {owner_group!r}")
if len(reason) > 1000:
    raise ValueError(f"reason is at most 1000 characters, not {len(reason)}")
if not re.fullmatch(r"[A-Za-z0-9._:/-]{0,100}", request_id):
    raise ValueError(f"request_id may only contain letters, digits and . _ : / -, not {request_id!r}")

# Only a request the app recorded, for these parameters (off unless jobs.require_request_record).
check_request_record(request_id, {"kind": "folder", "workspace": workspace_name, "requested_by": requested_by,
                                  "name": folder, "owner_group": owner_group})

w = WorkspaceClient()
me = list(w.users.list(filter=f'userName eq "{requested_by}"', attributes="id,userName,groups"))
if not me:
    raise ValueError(f"{requested_by} is not a user of this workspace")
my_groups = {g.display for g in me[0].groups or []}
if owner_group and owner_group not in my_groups:
    raise ValueError(f"{requested_by} is not in the group {owner_group}")

# COMMAND ----------

# An existing folder must already be managed by the requester or one of their groups:
# never hand someone else's folder over.
path = f"{root.rstrip('/')}/{folder}"
try:
    object_id = w.workspace.get_status(path).object_id
except NotFound:
    object_id = None
if object_id is not None:
    current = w.api_client.do("GET", f"/api/2.0/permissions/directories/{object_id}").get("access_control_list", [])
    managers = {a.get("user_name") or a.get("group_name") for a in current
                for p in a.get("all_permissions", []) if p["permission_level"] == "CAN_MANAGE" and not p.get("inherited")}
    if not managers & ({requested_by} | my_groups):
        raise ValueError(f"{path} already exists and is not managed by {requested_by} or their groups")
else:
    w.workspace.mkdirs(path)
    object_id = w.workspace.get_status(path).object_id

# The requester, their group and the platform admins can manage it. PATCH adds; it never
# removes anyone else's access.
acl = [{"user_name": requested_by, "permission_level": "CAN_MANAGE"}]
for g in dict.fromkeys(([owner_group] if owner_group else []) + admin_groups):
    acl.append({"group_name": g, "permission_level": "CAN_MANAGE"})
w.api_client.do("PATCH", f"/api/2.0/permissions/directories/{object_id}", body={"access_control_list": acl})
dbutils.notebook.exit(json.dumps({"path": path, "object_id": object_id, "owner_group": owner_group, "reason": reason, "request_id": request_id}))
