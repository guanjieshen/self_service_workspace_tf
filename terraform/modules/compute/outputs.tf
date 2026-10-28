output "default_warehouse_id" {
  value = databricks_sql_endpoint.default.id
}

output "team_warehouse_ids" {
  value = { for k, w in databricks_sql_endpoint.team : k => w.id }
}

output "shared_cluster_id" {
  value = try(databricks_cluster.shared[0].id, null)
}

output "cluster_policy_ids" {
  value = { for k, p in databricks_cluster_policy.persona : k => p.id }
}

output "classic_warehouse_id" {
  value = try(databricks_sql_endpoint.classic[0].id, null)
}
