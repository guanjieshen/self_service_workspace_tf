output "default_warehouse_id" {
  value = databricks_sql_endpoint.default.id
}

output "cluster_policy_id" {
  value = databricks_cluster_policy.classic.id
}
