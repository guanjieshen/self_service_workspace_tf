output "workspace" {
  value = try(local.workspace.host, null)
}

output "assigned_groups" {
  value = module.personas.assigned_groups
}

output "default_warehouse_id" {
  value = module.compute.default_warehouse_id
}

output "cluster_policy_id" {
  value = module.compute.cluster_policy_id
}

output "serverless_policy_ids" {
  value = try(module.budget_policies[0].policy_ids, {})
}

output "catalog" {
  value = try(module.catalog[0].name, null)
}

# Addresses of what this workspace leaves alone (settings set to null,
# serverless_policy.enabled false, genie-code managed: false; terraform/overrides.tf). scripts/tf.sh removes any of them still in the state
# before apply, and scripts/plan-guard.py reports their planned deletion as a release.
output "released_addresses" {
  value = local.released_addresses
}

