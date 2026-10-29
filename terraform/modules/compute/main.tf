locals {
  wh = var.sql_warehouse
  cp = var.cluster_policy

  access_mode_values = {
    STANDARD  = ["USER_ISOLATION", "DATA_SECURITY_MODE_STANDARD"]
    DEDICATED = ["SINGLE_USER", "DATA_SECURITY_MODE_DEDICATED"]
  }

  # The classic cluster policy. Optional elements use `{ for ... if cond }` so they
  # can be merged in or left out without type conflicts.
  policy_definition = merge(
    { for k, v in {
      spark_version = { type = "allowlist", values = ["auto:latest-lts", "auto:latest-lts-ml"], defaultValue = "auto:latest-lts" }
    } : k => v if local.cp.runtime == "lts_only" },
    {
      data_security_mode = {
        type         = "allowlist"
        values       = flatten([for m in local.cp.access_modes : local.access_mode_values[m]])
        defaultValue = local.access_mode_values[local.cp.access_modes[0]][0]
      }
      node_type_id            = { type = "allowlist", values = local.cp.node_types, defaultValue = local.cp.node_types[0] }
      driver_node_type_id     = { type = "allowlist", values = local.cp.node_types, defaultValue = local.cp.node_types[0] }
      num_workers             = { type = "range", maxValue = local.cp.max_workers }
      "autoscale.max_workers" = { type = "range", maxValue = local.cp.max_workers }
      autotermination_minutes = { type = "range", minValue = 10, maxValue = local.cp.max_autotermination_minutes, defaultValue = local.cp.max_autotermination_minutes }
    },
    # The chargeback tags are fixed on every cluster...
    { for k, v in var.tags : "custom_tags.${k}" => { type = "fixed", value = v } if !contains(var.classic_user_tags, k) },
    # ...except the ones the user fills in: required, one spelling, starting from the tag's value if it has one.
    {
      for k in var.classic_user_tags : "custom_tags.${k}" => merge(
        { type = "regex", pattern = var.user_tag_pattern, isOptional = false },
        { for d, v in { defaultValue = lookup(var.tags, k, null) } : d => v if v != null },
      )
    },
  )
}

# ---- Default SQL warehouse ----
# workspace_default: the admin setting "Default warehouse" (empty = each user's last selected).
resource "databricks_workspace_setting_v2" "default_warehouse" {
  count = try(local.wh.workspace_default, false) == true ? 1 : 0
  name  = "default_warehouse_id"
  string_val = {
    value = databricks_sql_endpoint.default.id
  }
}

resource "databricks_sql_endpoint" "default" {
  name                      = replace(replace(local.wh.name, "{BU}", var.names.BU), "{bu}", var.names.bu)
  cluster_size              = local.wh.size
  min_num_clusters          = local.wh.min_clusters
  max_num_clusters          = local.wh.max_clusters
  auto_stop_mins            = local.wh.auto_stop_minutes
  enable_serverless_compute = local.wh.type == "serverless"
  warehouse_type            = local.wh.type == "classic" ? "CLASSIC" : "PRO"

  tags {
    dynamic "custom_tags" {
      for_each = var.tags
      content {
        key   = custom_tags.key
        value = tostring(custom_tags.value)
      }
    }
  }
}

resource "databricks_permissions" "default_warehouse" {
  count           = length(var.warehouse_acl) + length(var.platform_admins) > 0 ? 1 : 0
  sql_endpoint_id = databricks_sql_endpoint.default.id

  dynamic "access_control" {
    for_each = merge(var.warehouse_acl, { for g in var.platform_admins : g => "CAN_MANAGE" })
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}

# ---- The classic cluster policy ----
# Who may use it is not managed here: the self-service app grants it on request, and
# managing its permissions would remove the app's grants. Workspace admins can always use it.
resource "databricks_cluster_policy" "classic" {
  name                  = replace(replace(local.cp.name, "{BU}", var.names.BU), "{bu}", var.names.bu)
  definition            = jsonencode(local.policy_definition)
  max_clusters_per_user = local.cp.max_clusters_per_user
}
