# Module inputs built from the configuration (named here so terraform/tests/ can check them).
locals {
  # Group names as the personas module returns them once assigned. Granting through
  # these makes each grant wait for its group's assignment, without a module-level
  # depends_on: that would defer every data source in the module until apply whenever
  # an assignment is planned, which plans permissions that read a data source as replaced.
  group = module.personas.group_names
}

module "personas" {
  source = "./modules/personas"

  personas                 = local.entitlement_personas
  persona_groups           = local.entitlement_groups
  platform_admins          = local.platform_admins
  platform_admin_role      = "ADMIN"
  extra_groups             = local.extra_groups
  users_group_entitlements = local.settings.users_group_entitlements

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}

module "workspace_settings" {
  source = "./modules/workspace-settings"

  settings                = local.settings
  default_catalog         = local.default_catalog
  workspace_label         = try(local.workspace.label, null)
  genie_code_instructions = local.manage_genie_instructions ? local.genie_instructions : null
  genie_code_skills       = local.manage_genie_skills ? local.genie_skills : {}
  token_groups            = [for g in local.token_groups : lookup(local.group, g, g)]
  platform_admins         = [for g in local.platform_admins : lookup(local.group, g, g)]

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}

# The Serverless Starter Warehouse Databricks creates in a new workspace, found by name (only
# its permissions are managed). Read here, not in the compute module: that module waits for
# config_checks, which on a first apply would defer its data sources, and for_each needs the
# IDs at plan time.
data "databricks_sql_warehouses" "starter" {
  count                   = try(local.config.starter_warehouse.admins_only, null) == true ? 1 : 0
  warehouse_name_contains = local.config.starter_warehouse.name
}

module "compute" {
  source = "./modules/compute"

  names             = { BU = local.bu_upper, bu = local.bu }
  tags              = local.chargeback_tags
  classic_user_tags = local.classic_user_tags
  user_tag_pattern  = local.user_tag_pattern
  sql_warehouse     = local.config.sql_warehouse
  cluster_policy    = local.config.cluster_policy
  warehouse_acl     = { for g, l in local.persona_acl.default_warehouse : lookup(local.group, g, g) => l }
  starter_warehouse = try(tolist(data.databricks_sql_warehouses.starter[0].ids), [])
  platform_admins   = [for g in local.platform_admins : lookup(local.group, g, g)]

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}

module "budget_policies" {
  source    = "./modules/budget-policies"
  count     = local.sp.enabled ? 1 : 0
  providers = { databricks = databricks.account }

  account_id   = local.account_id
  workspace_id = local.workspace_id
  policies     = local.serverless_policies
  managers     = [for g in local.platform_admins : "groups/${g}"]

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}

# The workspace's Unity Catalog catalog and its grants (config/defaults/catalog.yaml).
module "catalog" {
  source = "./modules/catalog"
  count  = local.catalog != null ? 1 : 0

  catalog = local.catalog
  grants  = { for g, privs in local.catalog_grants : lookup(local.group, g, g) => privs if length(privs) > 0 }

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}
