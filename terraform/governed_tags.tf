# Governed tags (config/defaults/governed-tags.yaml): account-wide tag policies. One state
# creates them, the self-service hub's workspace, with their allowed values read from every
# workspace file; each workspace puts its own value on its catalog.
#
# A workspace tags its catalog only once its value is allowed (the hub applied it): before
# that, the plan leaves the tag out instead of failing, and the next apply adds it. The hub's
# own catalog is tagged in the same apply that creates the tag.

locals {
  gt     = try(local.defaults.governed_tags, null)
  gt_key = try(tostring(local.gt.business_unit), null)
  # This workspace's state owns the governed tags when it is the self-service hub's (self_service.tf).
  gt_owner = local.gt_key != null && local.self_service_hub_host_id != null && local.self_service_hub_host_id == local.workspace_id
  gt_value = lower(local.prefix)

  # Every workspace file next to this one's: its prefix, and the groups it names (with the
  # baseline's platform admins), so the hub can allow every value and let every group assign it.
  gt_files      = [for f in fileset(coalesce(var.workspaces_dir, "${local.project_root}/config/workspaces"), "*.yaml") : f if !startswith(f, "_")]
  gt_workspaces = [for f in local.gt_files : try(yamldecode(file("${coalesce(var.workspaces_dir, "${local.project_root}/config/workspaces")}/${f}")), {})]
  gt_values     = sort(distinct([for w in local.gt_workspaces : lower(tostring(w.prefix)) if can(tostring(w.prefix))]))
  gt_assigners = sort(distinct(flatten([for w in local.gt_workspaces : [
    for k, g in merge(try(local.defaults.groups, {}), try(w.groups, {})) :
    replace(replace(tostring(g), "{PREFIX}", upper(tostring(w.prefix))), "{prefix}", lower(tostring(w.prefix)))
    if g != null && can(tostring(g))
  ] if can(tostring(w.prefix))])))
  gt_managers = try(tolist(local.gt.managers), null) != null ? [for g in local.gt.managers : tostring(g)] : local.platform_admins
  # The pipeline (this run's identity), like the usage policy's principals (self_service.tf).
  gt_pipeline = can(regex("@", data.databricks_current_user.me.user_name)) ? "users/${data.databricks_current_user.me.user_name}" : "servicePrincipals/${data.databricks_current_user.me.user_name}"

  # Outside the hub: tag the catalog once the governed tag allows this workspace's value.
  gt_existing = try([for p in data.databricks_tag_policies.all[0].tag_policies : p if p.tag_key == local.gt_key][0], null)
  gt_allowed  = local.gt_owner || contains(try([for v in local.gt_existing.values : v.name], []), local.gt_value)
}

resource "databricks_tag_policy" "business_unit" {
  count       = local.gt_owner ? 1 : 0
  tag_key     = local.gt_key
  description = "The business unit a catalog belongs to: its citizen development workspace's prefix. Managed by Terraform (config/defaults/governed-tags.yaml)."
  values      = [for v in local.gt_values : { name = v }]

  depends_on = [terraform_data.config_checks]
}

# Authoritative: who may change the tag, and who may put it on objects.
resource "databricks_access_control_rule_set" "business_unit" {
  count    = local.gt_owner ? 1 : 0
  provider = databricks.account
  name     = "accounts/${local.account_id}/tagPolicies/${databricks_tag_policy.business_unit[0].id}/ruleSets/default"

  grant_rules {
    principals = [for g in local.gt_managers : "groups/${g}"]
    role       = "roles/tagPolicy.manager"
  }
  grant_rules {
    principals = concat([for g in local.gt_assigners : "groups/${g}"], [local.gt_pipeline])
    role       = "roles/tagPolicy.assigner"
  }

  # The groups must exist in the account and be assigned to the workspace first.
  depends_on = [module.personas]
}

data "databricks_tag_policies" "all" {
  count = local.gt_key != null && !local.gt_owner && local.catalog != null ? 1 : 0
}

resource "databricks_entity_tag_assignment" "catalog_business_unit" {
  count       = local.gt_key != null && local.catalog != null && local.gt_allowed ? 1 : 0
  entity_type = "catalogs"
  entity_name = module.catalog[0].name
  tag_key     = local.gt_key
  tag_value   = local.gt_value

  depends_on = [databricks_tag_policy.business_unit, databricks_access_control_rule_set.business_unit]
}
