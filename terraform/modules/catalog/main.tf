# The workspace's Unity Catalog catalog and its schemas.
# Deleting a catalog or schema deletes its tables, views and volumes; force_destroy
# stays off so Terraform cannot delete one that still holds data.
locals {
  # Schemas differ in shape (some have grants), so work from their names.
  schema_names = try(keys(var.catalog.schemas), [])
  schema_grants = {
    for k in local.schema_names : k => try({ for p, privs in var.catalog.schemas[k].grants : p => tolist(privs) }, {})
  }
}

resource "databricks_catalog" "this" {
  name         = var.catalog.name
  comment      = try(var.catalog.comment, null)
  owner        = try(var.catalog.owner, null) # null = leave the owner alone
  storage_root = try(var.catalog.storage_root, null)
  # ISOLATED: only this workspace can use the catalog.
  isolation_mode = try(var.catalog.workspace_only, true) ? "ISOLATED" : "OPEN"
  # Schemas inherit it. null = leave alone.
  enable_predictive_optimization = try(var.catalog.predictive_optimization, null) == null ? null : (var.catalog.predictive_optimization ? "ENABLE" : "DISABLE")
}

# Data classification for the whole catalog (every schema, new ones too).
resource "databricks_data_classification_catalog_config" "this" {
  count  = try(var.catalog.data_classification, null) == true ? 1 : 0
  parent = "catalogs/${databricks_catalog.this.name}"
}

# Data quality monitoring (anomaly detection) on each shared schema.
resource "databricks_data_quality_monitor" "schema" {
  for_each                 = try(var.catalog.data_quality_monitoring, null) == true ? toset(local.schema_names) : toset([])
  object_type              = "schema"
  object_id                = databricks_schema.this[each.key].schema_id
  anomaly_detection_config = {}
}

resource "databricks_schema" "this" {
  for_each     = toset(local.schema_names)
  catalog_name = databricks_catalog.this.name
  name         = each.key
  comment      = try(var.catalog.schemas[each.key].comment, null)
}

# Who may use the catalog. Schemas, tables and views inherit these privileges.
# Authoritative: the list replaces any other grants on the catalog. The identity that
# runs Terraform and the personal schemas job keeps what it needs to manage schemas, and
# the job runners (jobs.runners) can see which schemas exist (BROWSE: metadata only, no
# data), so they can tell a user they already have their personal schema.
data "databricks_current_user" "me" {}

locals {
  catalog_grants = length(var.grants) == 0 ? {} : merge(var.grants,
    var.personal_schemas_enabled ? { (data.databricks_current_user.me.user_name) = ["ALL_PRIVILEGES", "MANAGE"] } : {},
  var.personal_schemas_enabled ? { for r in var.runners : r => ["BROWSE"] } : {})
}

resource "databricks_grants" "catalog" {
  count   = length(var.grants) > 0 ? 1 : 0
  catalog = databricks_catalog.this.name

  dynamic "grant" {
    for_each = local.catalog_grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

# Extra grants on individual schemas (catalog.yaml `schemas.<name>.grants`).
resource "databricks_grants" "schema" {
  for_each = { for k, g in local.schema_grants : k => g if length(g) > 0 }
  schema   = databricks_schema.this[each.key].id

  dynamic "grant" {
    for_each = each.value
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

# ---- Personal schemas ----
# A job creates one user's schema when an admin (or a runner, such as a ticketing system) asks: the
# notebook personal_schema.py creates it if it does not exist, tags it, grants it to the
# user and gives it to the owner group. Terraform deploys the job, not the schemas. The
# notebook lives in the admin folder, which only workspace admins can see, because the
# job runs with the rights to manage the catalog.
resource "databricks_notebook" "personal_schema" {
  count    = var.personal_schemas_enabled ? 1 : 0
  path     = "${var.admin_path}/personal_schema"
  language = "PYTHON"
  # The settings from catalog.yaml are written into the notebook, where a run cannot
  # change them (a run can pass any parameter, so they cannot be task parameters).
  content_base64 = base64encode(templatefile("${path.module}/personal_schema.py", {
    prefix           = var.personal_schemas.prefix
    privileges       = var.personal_schemas.privileges
    owner            = try(var.catalog.owner, null) == null ? "" : var.catalog.owner
    allowed_catalogs = [var.catalog.name]
  }))
}

resource "databricks_job" "personal_schemas" {
  count               = var.personal_schemas_enabled ? 1 : 0
  name                = var.personal_schemas.job_name
  max_concurrent_runs = 20 # requests run side by side, each on its own serverless compute

  queue {
    enabled = true # more requests than that wait their turn
  }

  # How automation finds the job, and the catalog it creates schemas in.
  tags = { cd_self_service = "personal_schema", cd_catalog = databricks_catalog.this.name, cd_prefix = var.personal_schemas.prefix }

  # What a request sets (the notebook explains each one).
  dynamic "parameter" {
    for_each = toset(["user", "catalog", "schema", "owner_group", "reason", "request_id"]) # all empty: each run sets them
    content {
      name    = parameter.value
      default = ""
    }
  }

  task {
    task_key        = "create"
    max_retries     = 0
    timeout_seconds = 600

    notebook_task {
      source        = "WORKSPACE"
      notebook_path = databricks_notebook.personal_schema[0].path
    }
  }
}

# Only workspace admins (and the owner) can see and run the job, plus these service
# principals (jobs.runners in access.yaml), for example a ticketing system's.
resource "databricks_permissions" "personal_schemas_job" {
  count  = var.personal_schemas_enabled && length(var.runners) > 0 ? 1 : 0
  job_id = databricks_job.personal_schemas[0].id

  dynamic "access_control" {
    for_each = var.runners
    content {
      service_principal_name = access_control.value
      permission_level       = "CAN_MANAGE_RUN"
    }
  }
}
