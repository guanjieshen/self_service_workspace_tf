# Module inputs built from the configuration (named here so terraform/tests/ can check them).
locals {
  team_warehouse_inputs = {
    for k, w in local.team_warehouses : k => { warehouse = w, group = try(local.teams[k].group, null), tags = try(local.teams[k].tags, {}) } if contains(keys(local.teams), k)
  }
  # One cluster policy per persona with cluster_policy: true and a group, tagged with its name.
  cluster_policies = {
    for p, def in local.personas : p => {
      template = local.config.cluster_policy
      tags     = { PERSONA = upper(p) }
      groups   = local.persona_groups[p]
      name = replace(replace(replace(local.config.cluster_policy.name,
      "{BU}", local.bu_upper), "{bu}", local.bu), "{PERSONA}", title(p))
    } if try(def.cluster_policy, false) == true && length(try(local.persona_groups[p], [])) > 0
  }

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

module "compute" {
  source = "./modules/compute"

  names              = { BU = local.bu_upper, bu = local.bu }
  workspace_tags     = local.workspace_tags
  sql_warehouse      = local.config.sql_warehouse
  classic_warehouse  = local.config.classic_warehouse
  team_warehouses    = { for k, w in local.team_warehouse_inputs : k => merge(w, { group = lookup(local.group, w.group, w.group) }) }
  shared_cluster     = local.config.shared_cluster
  allowed_tag_values = local.allowed_tag_values
  acl = {
    sql_warehouse  = { for g, l in local.persona_acl.default_warehouse : lookup(local.group, g, g) => l }
    shared_cluster = { for g, l in local.persona_acl.shared_cluster : lookup(local.group, g, g) => l }
  }
  platform_admins = [for g in local.platform_admins : lookup(local.group, g, g)]

  cluster_policies = { for p, cp in local.cluster_policies : p => merge(cp, { groups = [for g in cp.groups : lookup(local.group, g, g)] }) }

  # Invalid input stops at the plain-language checks in checks.tf, not a crash inside a
  # module. Harmless for the plan: config_checks has no inputs, so it only has changes
  # (and only defers this module's data sources) on a workspace's first apply.
  depends_on = [terraform_data.config_checks]
}

module "budget_policies" {
  source    = "./modules/budget-policies"
  count     = local.config.budget_policies.enabled ? 1 : 0
  providers = { databricks = databricks.account }

  account_id   = local.account_id
  workspace_id = local.workspace_id
  policies     = local.budget_policies
  managers     = local.budget_policy_managers

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
