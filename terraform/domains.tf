# Domains: groups inside one workspace with their own serverless usage policy, SQL warehouse
# and chargeback tags (their APPID), on top of the workspace's own (the catch-all).
#
#   domains:                              in the workspace's file only, never the baseline
#     finance:
#       groups: {explorer: [edm-gds-finance-explorer], builder: edm-gds-finance-builder}
#       tags: {APPID: APP-5678}           required: the domain's own APPID
#       serverless_policy: {name: ...}    optional: the default is {PREFIX}-0-DOMAIN-<NAME>
#       sql_warehouse: {size: Small}      optional: the baseline's sql_warehouse, key by key
#       folder: true                      optional: /Workspace/Domains/<Name>, for its groups only
#
# A domain's groups are persona groups (access.tf): they get their persona's access, the
# catch-all's warehouse and usage policy, and their domain's. The domain's policy is named to
# sort before the catch-all's ({PREFIX}-0-SELF-SERVICE), so it is the one its members' usage
# goes to when they do not pick one (config/defaults/cost.yaml). A workspace without domains changes nothing.
#
# Who owns what (docs/design.md): a domain is declared here, so its folder is too, and only the
# top folder: what people make inside it is theirs. Folders people ask for come from the
# self-service app, never under /Workspace/Domains (scripts/app_build.py refuses that folder_root).

locals {
  domains_in = try({ for d, v in local.ws_all.domains : d => v }, {})

  # {persona => [group]} per domain: a persona takes one group or a list, {prefix} filled in.
  domain_groups = {
    for d, v in local.domains_in : d => try({
      for p, gs in v.groups : p => [
        for g in flatten([gs]) : replace(replace(tostring(g), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)
      ] if gs != null
    }, {})
  }
  domain_members = { for d, ps in local.domain_groups : d => distinct(flatten(values(ps))) }
  domain_label   = { for d in keys(local.domains_in) : d => upper(replace(d, "_", "-")) }

  # The workspace's tags, then the domain's over them key by key (null drops one), and DOMAIN.
  domain_tags = {
    for d, v in local.domains_in : d => merge(
      {
        for k, x in merge(local.tag_values, try({ for k, x in v.tags : k => x }, {})) :
        k => replace(replace(tostring(x), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix) if x != null
      },
      { DOMAIN = local.domain_label[d] },
    )
  }

  domain_policies = {
    for d, v in local.domains_in : "domain_${d}" => {
      name       = replace(replace(try(tostring(v.serverless_policy.name), "{PREFIX}-0-DOMAIN-${local.domain_label[d]}"), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)
      tags       = local.domain_tags[d]
      groups     = distinct(concat(local.domain_members[d], local.platform_admins))
      principals = []
    }
  }

  # The baseline's warehouse (as this workspace has it), with the domain's keys over it.
  domain_warehouses = {
    for d, v in local.domains_in : d => merge(local.config.sql_warehouse, try({ for k, x in v.sql_warehouse : k => x }, {}), {
      name = replace(replace(try(tostring(v.sql_warehouse.name), "{PREFIX} ${title(lower(replace(d, "_", " ")))} Warehouse"), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)
    })
  }
  # The domain's own folder (folder: true): its groups only, not the workspace's own persona
  # groups. Groups of a persona with workspace access manage it; the others may read it.
  domain_folders = { for d, v in local.domains_in : d => "/Workspace/Domains/${title(lower(replace(d, "_", " ")))}" if try(v.folder, false) == true }
  domain_folder_acl = {
    for d in keys(local.domain_folders) : d => merge(
      merge([for p, gs in local.domain_groups[d] : { for g in gs : g => try(local.personas[p].access, "") == "workspace" ? "CAN_MANAGE" : "CAN_READ" }]...),
      { for g in local.platform_admins : g => "CAN_MANAGE" },
    )
  }

  domain_warehouse_acl = {
    for d, members in local.domain_members : d => merge(
      { for g in members : g => "CAN_USE" },
      { for g in local.platform_admins : g => "CAN_MANAGE" },
    )
  }
}

resource "databricks_sql_endpoint" "domain" {
  for_each                  = local.domain_warehouses
  name                      = each.value.name
  cluster_size              = each.value.size
  min_num_clusters          = each.value.min_clusters
  max_num_clusters          = each.value.max_clusters
  auto_stop_mins            = each.value.auto_stop_minutes
  enable_serverless_compute = each.value.type == "serverless"
  warehouse_type            = each.value.type == "classic" ? "CLASSIC" : "PRO"

  tags {
    dynamic "custom_tags" {
      for_each = local.domain_tags[each.key]
      content {
        key   = custom_tags.key
        value = custom_tags.value
      }
    }
  }

  depends_on = [terraform_data.config_checks]
}

# Authoritative, as the default warehouse's: the domain's groups may use it, admins manage it.
resource "databricks_permissions" "domain_warehouse" {
  for_each        = local.domain_warehouses
  sql_endpoint_id = databricks_sql_endpoint.domain[each.key].id

  dynamic "access_control" {
    for_each = local.domain_warehouse_acl[each.key]
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }

  # The groups must be assigned to the workspace before they can be granted.
  depends_on = [module.personas]
}

# Never deleted with what is in it: removing the domain or its folder: true plans a delete (the
# plan guard lists it under Before merging), which Databricks refuses while the folder is not empty.
resource "databricks_directory" "domain" {
  for_each         = local.domain_folders
  path             = each.value
  delete_recursive = false

  depends_on = [terraform_data.config_checks]
}

# Authoritative on the top folder only: sharing it by hand is undone; what is inside inherits it.
resource "databricks_permissions" "domain_folder" {
  for_each       = local.domain_folders
  directory_path = databricks_directory.domain[each.key].path

  dynamic "access_control" {
    for_each = local.domain_folder_acl[each.key]
    content {
      group_name       = access_control.key
      permission_level = access_control.value
    }
  }

  depends_on = [module.personas]
}
