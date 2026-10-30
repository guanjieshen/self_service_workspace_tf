output "policy_ids" {
  value = { for k, p in databricks_budget_policy.this : p.policy_name => p.policy_id }
  # Usable only once its users are granted (data classification waits on this).
  depends_on = [databricks_access_control_rule_set.this]
}
