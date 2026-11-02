output "dashboard" {
  description = "The cost dashboard's path in the central workspace."
  value       = try("${databricks_dashboard.cost[0].parent_path}/${databricks_dashboard.cost[0].display_name}", null)
}

output "view" {
  description = "The view the dashboard reads."
  value       = local.enabled ? local.view_name : null
}

output "released_addresses" {
  description = "Nothing here is released: scripts/tf.sh reads this output for every target."
  value       = []
}
