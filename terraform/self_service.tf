# What the self-service app needs in a workspace it serves (a spoke), granted here because
# Terraform owns these objects, authoritatively: the bundle (bundle/) deploys the app and its
# jobs and never grants on them itself (docs/design.md, "Who owns what").
#
#   - its two service principals (config/self-service/hub.yaml app_ids) are assigned to the
#     workspace, and may see the catalog (USE CATALOG, BROWSE: the app checks whether a
#     person's schema exists);
#   - the identity running Terraform, which also deploys and runs the self-service jobs, may use
#     the workspace's serverless usage policy, so the jobs can run on it.
#
# A workspace opts out with self_service: false in its file (for example the hub itself).
# Nothing here exists until app_ids are set, after the app's first deploy.

locals {
  self_service_dir     = coalesce(var.self_service_dir, "${local.project_root}/config/self-service")
  self_service_hub     = try(yamldecode(file("${local.self_service_dir}/hub.yaml")), {})
  self_service_enabled = try(local.ws_all.self_service, true) != false
  self_service_app_ids = local.self_service_enabled ? compact([
    for k in ["self_service", "approvals"] : try(tostring(local.self_service_hub.app_ids[k]), "")
  ]) : []

  # The usage policy's users are groups (chargeback.tf) plus, here, the identity running
  # Terraform: a service principal in CI (its application ID), a person when run locally.
  pipeline_principal = local.self_service_enabled ? [
    can(regex("@", data.databricks_current_user.me.user_name)) ? "users/${data.databricks_current_user.me.user_name}" : "servicePrincipals/${data.databricks_current_user.me.user_name}"
  ] : []
}

data "databricks_current_user" "me" {}

resource "databricks_permission_assignment" "self_service_app" {
  for_each               = toset(local.self_service_app_ids)
  service_principal_name = each.value
  permissions            = ["USER"]

  depends_on = [terraform_data.config_checks]
}

# What the self-service app's deploy reads (scripts/app_deploy.py), so it never repeats a value
# this workspace's configuration already has.
output "self_service" {
  value = {
    enabled         = local.self_service_enabled
    prefix          = local.prefix
    id              = local.workspace_id
    host            = try(trimsuffix(local.workspace.host, "/"), null)
    catalog         = try(local.catalog.name, null)
    usage_policy_id = try(module.budget_policies[0].policy_ids[local.serverless_policies.self_service.name], null)
  }
}
