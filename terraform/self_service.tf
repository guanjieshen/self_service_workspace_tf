# What the self-service app needs in a workspace it serves (a spoke), granted here because
# Terraform owns these objects, authoritatively: the app's own deploy (a Databricks Asset
# Bundle) deploys the app and its jobs and never grants on them itself.
#
#   - its two service principals (config/self-service/hub.yaml app_ids) are assigned to the
#     workspace, with workspace access (the baseline gives the users group no entitlements, so
#     without it they could not use the Jobs API), and may see the catalog (USE CATALOG,
#     BROWSE: the app checks whether a person's schema exists);
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

  # The hub (hub.yaml host): this workspace's schema job runs there (scripts/app_build.py
  # jobs_target), so the catalog and the usage policy are bound to it too. null: no hub yet, or
  # this workspace is the hub, or it is not served.
  self_service_hub_host_id = try(regex("adb-([0-9]+)\\.", tostring(local.self_service_hub.hub.host))[0], null)
  self_service_hub_id = (local.self_service_enabled && local.self_service_hub_host_id != null
  && local.self_service_hub_host_id != local.workspace_id) ? local.self_service_hub_host_id : null

  # The usage policy's users are groups (chargeback.tf) plus, here, the identity running
  # Terraform: a service principal in CI (its application ID), a person when run locally.
  pipeline_principal = local.self_service_enabled ? [
    can(regex("@", data.databricks_current_user.me.user_name)) ? "users/${data.databricks_current_user.me.user_name}" : "servicePrincipals/${data.databricks_current_user.me.user_name}"
  ] : []
}

data "databricks_current_user" "me" {}

# The catalog is bound to this workspace (workspace_only); bound to the hub too, read and write,
# so the schema job there can create schemas in it. Only principals granted on the catalog can use
# it there (the pipeline's identity, the platform admins): binding gives nobody access by itself.
resource "databricks_workspace_binding" "self_service_hub" {
  count          = local.self_service_hub_id != null && local.catalog != null ? 1 : 0
  securable_name = module.catalog[0].name
  securable_type = "catalog"
  workspace_id   = tonumber(local.self_service_hub_id)
  binding_type   = "BINDING_TYPE_READ_WRITE"
}

resource "databricks_permission_assignment" "self_service_app" {
  for_each               = toset(local.self_service_app_ids)
  service_principal_name = each.value
  permissions            = ["USER"]

  depends_on = [terraform_data.config_checks]
}

# Workspace access, so the apps can call the Jobs API here: list the self-service jobs (they
# may run only those, by the jobs' own permissions) and follow their runs.
data "databricks_service_principal" "self_service_app" {
  for_each       = toset(local.self_service_app_ids)
  application_id = each.value
  depends_on     = [databricks_permission_assignment.self_service_app]
}

resource "databricks_entitlements" "self_service_app" {
  for_each             = toset(local.self_service_app_ids)
  service_principal_id = data.databricks_service_principal.self_service_app[each.value].id
  workspace_access     = true

  # The lookup waits for the assignment, so the ID is unknown while one is planned; it never
  # changes for an application ID, so a planned assignment must not replace this.
  lifecycle {
    ignore_changes = [service_principal_id]
  }
}

# What the self-service app's deploy reads, so it never repeats a value
# this workspace's configuration already has.
output "self_service" {
  value = {
    enabled         = local.self_service_enabled
    prefix          = local.prefix
    id              = local.workspace_id
    host            = try(trimsuffix(local.workspace.host, "/"), null)
    catalog         = try(local.catalog.name, null)
    usage_policy_id = try(module.budget_policies[0].policy_ids[local.serverless_policies.self_service.name], null)
    platform_admins = local.platform_admins # the folder job gives them CAN_MANAGE on every folder it creates
  }
}
