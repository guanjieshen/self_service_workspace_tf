# Account-level resources: this module must be given the account-level provider.

resource "databricks_budget_policy" "this" {
  for_each              = var.policies
  policy_name           = each.value.name
  binding_workspace_ids = [var.workspace_id]
  custom_tags           = [for k, v in each.value.tags : { key = k, value = tostring(v) }]
}

# Who may use (and manage) each policy. This is authoritative: it replaces any
# grants made by hand, so every intended principal must be listed here.
resource "databricks_access_control_rule_set" "this" {
  for_each = var.policies
  name     = "accounts/${var.account_id}/budgetPolicies/${databricks_budget_policy.this[each.key].policy_id}/ruleSets/default"

  dynamic "grant_rules" {
    for_each = length(each.value.groups) > 0 ? [1] : []
    content {
      principals = concat([for g in each.value.groups : "groups/${g}"], try(each.value.users, []))
      role       = "roles/budgetPolicy.user"
    }
  }

  dynamic "grant_rules" {
    for_each = length(var.managers) > 0 ? [1] : []
    content {
      principals = var.managers
      role       = "roles/budgetPolicy.manager"
    }
  }
}
