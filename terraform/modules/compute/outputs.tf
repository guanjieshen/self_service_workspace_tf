output "default_warehouse_id" {
  value = databricks_sql_endpoint.default.id
}

output "cluster_policy_ids" {
  value = { for k, p in databricks_cluster_policy.classic : k => p.id }
}
