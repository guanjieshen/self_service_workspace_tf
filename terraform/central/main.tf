# The cost dashboard in the central workspace (config/central.yaml, cost_dashboard):
# a schema and a view over the billing system tables, a warehouse, the dashboard, and who may
# open it. Each person sees only the workspaces they belong to: the view filters its rows by
# the viewer's groups, and the dashboard runs with the viewer's own credentials.

locals {
  n = local.enabled ? 1 : 0

  # The account's usage policies, by name, that are bound to a managed workspace (or to all).
  our_ids = [for m in values(local.members) : m.id]
  policy_names = var.policy_names != null ? var.policy_names : local.enabled ? {
    for p in data.databricks_budget_policies.all[0].policies : p.policy_id => p.policy_name
    if length(try(p.binding_workspace_ids, [])) == 0 || length(setintersection(toset([for w in try(p.binding_workspace_ids, []) : tostring(w)]), toset(local.our_ids))) > 0
  } : {}

  # The VALUES lists the view needs, quoted for SQL (a ' doubled).
  sql_rows = {
    workspaces = length(local.members) == 0 ? "('-', '-')" : join(", ", [for m in values(local.members) : "('${m.id}', '${replace(m.prefix, "'", "''")}')"])
    access     = length(local.access) == 0 ? "('-', '-')" : join(", ", [for a in local.access : "('${a.workspace_id}', '${replace(a.group, "'", "''")}')"])
    admins     = length(local.members) == 0 ? "('-', '-')" : join(", ", [for m in values(local.members) : "('${m.id}', '${replace(m.admins, "'", "''")}')"])
    policies   = length(local.policy_names) == 0 ? "('-', '-')" : join(", ", [for id, name in local.policy_names : "('${id}', '${replace(name, "'", "''")}')"])
  }
  view_sql = templatefile("${path.module}/usage_cost.sql.tftpl", merge(local.sql_rows, { discount = local.discount_percent }))

  warehouse_id = local.given_warehouse != null ? local.given_warehouse : try(databricks_sql_endpoint.dashboard[0].id, null)
  view_name    = "${coalesce(local.catalog, "-")}.${local.schema}.usage_cost"
}

data "databricks_budget_policies" "all" {
  count    = local.enabled && var.policy_names == null ? 1 : 0
  provider = databricks.account
}

# ---- The warehouse: the one given, or a small serverless one ----
resource "databricks_sql_endpoint" "dashboard" {
  count                     = local.enabled && local.given_warehouse == null ? 1 : 0
  name                      = local.dashboard_name
  cluster_size              = local.warehouse_size
  min_num_clusters          = 1
  max_num_clusters          = 1
  auto_stop_mins            = 5
  enable_serverless_compute = true
  warehouse_type            = "PRO"
  depends_on                = [terraform_data.config_checks]
}

resource "databricks_permissions" "warehouse" {
  count           = length(databricks_sql_endpoint.dashboard)
  sql_endpoint_id = databricks_sql_endpoint.dashboard[0].id
  dynamic "access_control" {
    for_each = toset(local.viewer_groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}

# ---- The view, in its own schema ----
resource "databricks_schema" "cost" {
  count        = local.n
  catalog_name = local.catalog
  name         = local.schema
  comment      = "Cost of citizen development workspaces (managed by Terraform, terraform/central)"
  depends_on   = [terraform_data.config_checks]
}

resource "databricks_sql_table" "usage_cost" {
  count           = local.n
  catalog_name    = local.catalog
  schema_name     = databricks_schema.cost[0].name
  name            = "usage_cost"
  table_type      = "VIEW"
  view_definition = local.view_sql
  warehouse_id    = local.warehouse_id
  comment         = "Usage and estimated cost per workspace, usage policy, project and product; each viewer sees only their workspaces"
}

# Reaching the view: USE CATALOG (not authoritative: the catalog is someone else's), and
# USE SCHEMA and SELECT on the schema this module owns (authoritative).
resource "databricks_grant" "catalog" {
  for_each   = local.enabled ? toset(local.viewer_groups) : toset([])
  catalog    = local.catalog
  principal  = each.value
  privileges = ["USE_CATALOG"]
}

resource "databricks_grants" "schema" {
  count  = local.enabled && length(local.viewer_groups) > 0 ? 1 : 0
  schema = "${local.catalog}.${databricks_schema.cost[0].name}"
  dynamic "grant" {
    for_each = toset(local.viewer_groups)
    content {
      principal  = grant.value
      privileges = ["SELECT", "USE_SCHEMA"]
    }
  }
}

# ---- People from other workspaces: consumer access to the central workspace ----
resource "databricks_permission_assignment" "viewers" {
  for_each    = local.enabled ? toset(local.external_groups) : toset([])
  group_name  = each.value
  permissions = ["USER"]
}

data "databricks_group" "viewers" {
  for_each     = local.enabled ? toset(local.external_groups) : toset([])
  display_name = each.value
  depends_on   = [databricks_permission_assignment.viewers]
}

resource "databricks_entitlements" "viewers" {
  for_each          = local.enabled ? toset(local.external_groups) : toset([])
  group_id          = data.databricks_group.viewers[each.key].id
  workspace_consume = true
}

# ---- The dashboard ----
resource "databricks_directory" "folder" {
  count = local.n
  path  = local.folder
}

resource "databricks_dashboard" "cost" {
  count        = local.n
  display_name = local.dashboard_name
  parent_path  = databricks_directory.folder[0].path
  warehouse_id = local.warehouse_id
  serialized_dashboard = templatefile("${path.module}/cost.lvdash.json.tftpl", {
    view     = local.view_name
    discount = local.discount_percent
  })
  # Each viewer's own credentials: the view's row filter applies to them.
  embed_credentials = false
  depends_on        = [databricks_sql_table.usage_cost]
}

resource "databricks_permissions" "dashboard" {
  count        = local.enabled && length(local.viewer_groups) > 0 ? 1 : 0
  dashboard_id = databricks_dashboard.cost[0].id
  dynamic "access_control" {
    for_each = toset(local.viewer_groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_RUN"
    }
  }
}
