locals {
  persona_group_list = distinct(flatten(values(var.persona_groups)))

  group_personas = {
    for g in local.persona_group_list : g => [for p, gs in var.persona_groups : p if contains(gs, g)]
  }

  # Workspace assignment: platform admins get their role; everyone else is USER.
  assignments = merge(
    { for g in distinct(concat(local.persona_group_list, var.extra_groups)) : g => ["USER"] },
    { for g in var.platform_admins : g => [var.platform_admin_role] },
  )

  # A group in several personas gets the union of their entitlements.
  entitlement_union = {
    for g, ps in local.group_personas : g => {
      for e in ["workspace_access", "workspace_consume", "databricks_sql_access", "allow_cluster_create"] :
      e => anytrue([for p in ps : try(var.personas[p].entitlements[e], false)])
    } if !contains(var.platform_admins, g)
  }
  # Access comes in tiers, and the provider accepts consumer access only on its own:
  #   consumer access (Databricks One) < Databricks SQL access < workspace access.
  # A group gets the highest tier any of its personas has; consumer access is set only
  # when the group has neither of the others (and then they are left unset).
  entitlements = {
    for g, e in local.entitlement_union : g => merge(e, {
      workspace_consume     = local.consumer_only[g] ? true : null
      workspace_access      = local.consumer_only[g] ? null : e.workspace_access
      databricks_sql_access = local.consumer_only[g] ? null : e.databricks_sql_access
    })
  }
  consumer_only = { for g, e in local.entitlement_union : g => e.workspace_consume && !e.workspace_access && !e.databricks_sql_access }
}

resource "databricks_permission_assignment" "this" {
  for_each    = local.assignments
  group_name  = each.key
  permissions = each.value
}

data "databricks_group" "persona" {
  for_each     = local.entitlements
  display_name = each.key
  depends_on   = [databricks_permission_assignment.this]
}

resource "databricks_entitlements" "persona" {
  for_each              = local.entitlements
  group_id              = data.databricks_group.persona[each.key].id
  workspace_access      = each.value.workspace_access
  workspace_consume     = each.value.workspace_consume
  databricks_sql_access = each.value.databricks_sql_access
  allow_cluster_create  = each.value.allow_cluster_create

  # The group lookup waits for workspace assignment, so while an assignment is planned
  # the ID is unknown, and group_id forces a replacement: every persona group's
  # entitlements would show as replaced (a false risky change) when one group is added.
  # The key is the group's name, so its ID does not change.
  lifecycle {
    ignore_changes = [group_id]
  }
}

# Built-in "users" group. Destroying this resource removes these entitlements from it.
locals {
  users_consumer_only = try(var.users_group_entitlements.workspace_consume, false) == true && try(var.users_group_entitlements.workspace_access, false) != true && try(var.users_group_entitlements.databricks_sql_access, false) != true
}

data "databricks_group" "users" {
  count        = var.users_group_entitlements != null ? 1 : 0
  display_name = "users"
}

resource "databricks_entitlements" "users" {
  count                 = var.users_group_entitlements != null ? 1 : 0
  group_id              = data.databricks_group.users[0].id
  workspace_access      = local.users_consumer_only ? null : try(var.users_group_entitlements.workspace_access, false)
  workspace_consume     = local.users_consumer_only ? true : null
  databricks_sql_access = local.users_consumer_only ? null : try(var.users_group_entitlements.databricks_sql_access, false)
  allow_cluster_create  = try(var.users_group_entitlements.allow_cluster_create, false)
}
