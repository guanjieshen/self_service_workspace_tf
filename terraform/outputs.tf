output "workspace" {
  value = try(local.workspace.host, null)
}

output "assigned_groups" {
  value = module.personas.assigned_groups
}

output "default_warehouse_id" {
  value = module.compute.default_warehouse_id
}

output "classic_warehouse_id" {
  value = module.compute.classic_warehouse_id
}

output "team_warehouse_ids" {
  value = module.compute.team_warehouse_ids
}

output "shared_cluster_id" {
  value = module.compute.shared_cluster_id
}

output "cluster_policy_ids" {
  value = module.compute.cluster_policy_ids
}

output "budget_policy_ids" {
  value = try(module.budget_policies[0].policy_ids, {})
}

# The job that creates a team folder on request (run it with team and group).
output "team_folder_job_id" {
  value = module.folders.team_folder_job_id
}

# The job that creates one user's personal schema on request (run it with user).
output "personal_schema_job_id" {
  value = try(module.catalog[0].personal_schema_job_id, null)
}

output "catalog" {
  value = try(module.catalog[0].name, null)
}

# Addresses of what this workspace leaves alone (settings set to null, manage switches and
# budget_policies.enabled false, genie-code managed: false; terraform/overrides.tf). scripts/tf.sh removes any of them still in the state
# before apply, and scripts/plan-guard.py reports their planned deletion as a release.
output "released_addresses" {
  value = local.released_addresses
}

