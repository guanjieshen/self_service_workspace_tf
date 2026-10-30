output "default_warehouse_id" {
  value = databricks_sql_endpoint.default.id
}

output "starter_warehouse_permissions" {
  description = "Starter warehouse ID => its grants (group=level), for the tests."
  value       = { for id, p in databricks_permissions.starter_warehouse : id => [for a in p.access_control : "${a.group_name}=${a.permission_level}"] }
}

output "cluster_policy_ids" {
  value = { for k, p in databricks_cluster_policy.classic : k => p.id }
}
