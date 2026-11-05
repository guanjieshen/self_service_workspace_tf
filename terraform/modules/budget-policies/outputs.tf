output "policy_ids" {
  value = { for k, p in databricks_budget_policy.this : p.policy_name => p.policy_id }
}
