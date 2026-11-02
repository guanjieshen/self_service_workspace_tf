output "dashboards" {
  description = "The cost dashboards in the central workspace: everyone's, and the platform admins'."
  value = local.enabled ? {
    users  = "${local.folder}/${local.users_dashboard}"
    admins = "${local.folder}/${local.dashboard_name}"
  } : null
}

output "view" {
  description = "The view the dashboard reads."
  value       = local.enabled ? local.view_name : null
}

output "released_addresses" {
  description = "Nothing here is released: scripts/tf.sh reads this output for every target."
  value       = []
}
