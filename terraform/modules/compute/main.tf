locals {
  wh = var.sql_warehouse

  lob_tag = { LOB = var.lob }

  default_wh_tags = merge(local.lob_tag, try(local.wh.tags, {}))

  team_wh = {
    for k, t in var.team_warehouses : k => {
      settings = t.warehouse
      tags     = merge(local.lob_tag, t.tags)
      group    = t.group
      name     = t.warehouse.name
    }
  }

  # Databricks adds these to single-node clusters after creation; declaring them
  # keeps the plan clean (otherwise every run would try to remove them).
  single_node_tags = var.shared_cluster.single_node ? { ResourceClass = "SingleNode" } : {}
  single_node_conf = var.shared_cluster.single_node ? {
    "spark.databricks.cluster.profile" = "singleNode"
    "spark.master"                     = "local[*, 4]"
  } : {}

  access_mode_values = {
    STANDARD  = ["USER_ISOLATION", "DATA_SECURITY_MODE_STANDARD"]
    DEDICATED = ["SINGLE_USER", "DATA_SECURITY_MODE_DEDICATED"]
  }

  # Cluster policy definitions. Optional elements use `{ for ... if cond }` so they
  # can be merged in or left out without type conflicts.
  policy_definitions = {
    for p, cp in var.cluster_policies : p => merge(
      { for k, v in {
        spark_version = { type = "allowlist", values = ["auto:latest-lts", "auto:latest-lts-ml"], defaultValue = "auto:latest-lts" }
      } : k => v if cp.template.runtime == "lts_only" },
      {
        data_security_mode = {
          type         = "allowlist"
          values       = flatten([for m in cp.template.access_modes : local.access_mode_values[m]])
          defaultValue = local.access_mode_values[cp.template.access_modes[0]][0]
        }
        node_type_id            = { type = "allowlist", values = cp.template.node_types, defaultValue = cp.template.node_types[0] }
        driver_node_type_id     = { type = "allowlist", values = cp.template.node_types, defaultValue = cp.template.node_types[0] }
        num_workers             = { type = "range", maxValue = cp.template.max_workers }
        "autoscale.max_workers" = { type = "range", maxValue = cp.template.max_workers }
        autotermination_minutes = { type = "range", minValue = 10, maxValue = cp.template.max_autotermination_minutes, defaultValue = cp.template.max_autotermination_minutes }
      },
      { for k, v in merge(local.lob_tag, cp.tags) : "custom_tags.${k}" => { type = "fixed", value = tostring(v) } },
      {
        for tag, values in var.allowed_tag_values : "custom_tags.${tag}" => [
          { type = "allowlist", values = values, isOptional = false },
          { type = "unlimited", isOptional = false },
        ][length(values) > 0 ? 0 : 1]
      },
    )
  }
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
      for_each = local.default_wh_tags
      content {
        key   = custom_tags.key
        value = tostring(custom_tags.value)
      }
    }
  }
}

resource "databricks_permissions" "default_warehouse" {
  count           = length(var.acl.sql_warehouse) + length(var.platform_admins) > 0 ? 1 : 0
  sql_endpoint_id = databricks_sql_endpoint.default.id

  dynamic "access_control" {
    for_each = merge(var.acl.sql_warehouse, { for g in var.platform_admins : g => "CAN_MANAGE" })
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}

# Optional second warehouse on classic compute, for work that needs it (for example
# a private network path serverless does not have yet). Same access as the default.
locals {
  classic_wh = var.classic_warehouse
}

resource "databricks_sql_endpoint" "classic" {
  count                     = try(local.classic_wh.enabled, false) == true ? 1 : 0
  name                      = replace(replace(local.classic_wh.name, "{BU}", var.names.BU), "{bu}", var.names.bu)
  cluster_size              = local.classic_wh.size
  min_num_clusters          = local.classic_wh.min_clusters
  max_num_clusters          = local.classic_wh.max_clusters
  auto_stop_mins            = local.classic_wh.auto_stop_minutes
  enable_serverless_compute = false
  warehouse_type            = local.classic_wh.type == "pro" ? "PRO" : "CLASSIC"

  tags {
    dynamic "custom_tags" {
      for_each = merge(local.lob_tag, try(local.classic_wh.tags, {}))
      content {
        key   = custom_tags.key
        value = tostring(custom_tags.value)
      }
    }
  }
}

resource "databricks_permissions" "classic_warehouse" {
  count           = length(databricks_sql_endpoint.classic) > 0 && length(var.acl.sql_warehouse) + length(var.platform_admins) > 0 ? 1 : 0
  sql_endpoint_id = databricks_sql_endpoint.classic[0].id

  dynamic "access_control" {
    for_each = merge(var.acl.sql_warehouse, { for g in var.platform_admins : g => "CAN_MANAGE" })
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}

# ---- Team warehouses (chargeback) ----
resource "databricks_sql_endpoint" "team" {
  for_each                  = local.team_wh
  name                      = each.value.name
  cluster_size              = each.value.settings.size
  min_num_clusters          = each.value.settings.min_clusters
  max_num_clusters          = each.value.settings.max_clusters
  auto_stop_mins            = each.value.settings.auto_stop_minutes
  enable_serverless_compute = each.value.settings.type == "serverless"
  warehouse_type            = each.value.settings.type == "classic" ? "CLASSIC" : "PRO"

  tags {
    dynamic "custom_tags" {
      for_each = each.value.tags
      content {
        key   = custom_tags.key
        value = tostring(custom_tags.value)
      }
    }
  }
}

resource "databricks_permissions" "team_warehouse" {
  for_each        = local.team_wh
  sql_endpoint_id = databricks_sql_endpoint.team[each.key].id

  dynamic "access_control" {
    for_each = merge({ (each.value.group) = "CAN_USE" }, { for g in var.platform_admins : g => "CAN_MANAGE" })
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}

# ---- Shared classic cluster ----
data "databricks_spark_version" "lts" {
  count             = var.shared_cluster.enabled && var.shared_cluster.runtime == "latest_lts" ? 1 : 0
  long_term_support = true
}

resource "databricks_cluster" "shared" {
  count                   = var.shared_cluster.enabled ? 1 : 0
  cluster_name            = replace(replace(var.shared_cluster.name, "{BU}", var.names.BU), "{bu}", var.names.bu)
  spark_version           = var.shared_cluster.runtime == "latest_lts" ? data.databricks_spark_version.lts[0].id : var.shared_cluster.runtime
  node_type_id            = var.shared_cluster.node_type
  kind                    = "CLASSIC_PREVIEW"
  is_single_node          = var.shared_cluster.single_node
  num_workers             = var.shared_cluster.single_node ? 0 : var.shared_cluster.num_workers
  data_security_mode      = "DATA_SECURITY_MODE_STANDARD"
  autotermination_minutes = var.shared_cluster.autotermination_minutes
  custom_tags             = merge({ for k, v in merge(local.lob_tag, try(var.shared_cluster.tags, {})) : k => tostring(v) }, local.single_node_tags)
  spark_conf              = local.single_node_conf
  no_wait                 = true # do not wait for the cluster to start on create
}

resource "databricks_permissions" "shared_cluster" {
  count      = var.shared_cluster.enabled && length(var.acl.shared_cluster) > 0 ? 1 : 0
  cluster_id = databricks_cluster.shared[0].id

  dynamic "access_control" {
    for_each = var.acl.shared_cluster
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }
}

# ---- Cluster policies, one per persona ----
resource "databricks_cluster_policy" "persona" {
  for_each              = var.cluster_policies
  name                  = each.value.name
  definition            = jsonencode(local.policy_definitions[each.key])
  max_clusters_per_user = each.value.template.max_clusters_per_user
}

resource "databricks_permissions" "cluster_policy" {
  for_each          = var.cluster_policies
  cluster_policy_id = databricks_cluster_policy.persona[each.key].id

  dynamic "access_control" {
    for_each = toset(each.value.groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
