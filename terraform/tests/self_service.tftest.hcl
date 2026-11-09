# The self-service app's needs in a workspace it serves (terraform/self_service.tf):
# its service principals granted on the catalog (never assigned: the app calls only the hub), the jobs' identity on the usage
# policy, and the output the app's deploy reads.

mock_provider "databricks" {
  override_data {
    target = data.databricks_current_user.me
    values = { user_name = "33333333-3333-3333-3333-333333333333" }
  }
}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures"
  self_service_dir = "tests/self-service"
  use_cli_profiles = false
}

run "served_workspace" {
  command = plan
  variables { workspace = "basic" }

  assert {
    condition     = local.catalog_grants["11111111-1111-1111-1111-111111111111"] == tolist(["BROWSE", "USE_CATALOG"]) && local.catalog_grants["22222222-2222-2222-2222-222222222222"] == tolist(["BROWSE", "USE_CATALOG"])
    error_message = "The apps may see the catalog (USE CATALOG, BROWSE) and nothing more."
  }
  assert {
    condition     = local.serverless_policies.self_service.principals == tolist(["servicePrincipals/33333333-3333-3333-3333-333333333333"])
    error_message = "The identity running Terraform (which runs the self-service jobs) may use the usage policy."
  }
  assert {
    condition     = output.self_service.enabled && output.self_service.prefix == "tst" && output.self_service.id == "1111111111111111" && output.self_service.host == "https://adb-1111111111111111.1.azuredatabricks.net" && output.self_service.catalog == "tst_citizen_dev" && output.self_service.platform_admins == local.platform_admins && length(output.self_service.platform_admins) > 0
    error_message = "The output gives the app's deploy what this workspace's configuration already has."
  }
  assert {
    condition     = length(databricks_workspace_binding.self_service_hub) == 1 && databricks_workspace_binding.self_service_hub[0].workspace_id == 9999999999999999 && databricks_workspace_binding.self_service_hub[0].binding_type == "BINDING_TYPE_READ_WRITE" && databricks_workspace_binding.self_service_hub[0].securable_type == "catalog"
    error_message = "The catalog is bound to the hub too, read and write: this workspace's schema job runs there."
  }
  assert {
    condition     = local.self_service_hub_id == "9999999999999999"
    error_message = "The usage policy is bound to the hub too (main.tf extra_workspace_ids), so the job runs on it there."
  }
}

run "the_hub_never_binds_to_itself" {
  command = plan
  variables {
    workspace        = "basic"
    self_service_dir = "tests/self-service-hub-is-this-workspace"
  }

  assert {
    condition     = length(databricks_workspace_binding.self_service_hub) == 0 && local.self_service_hub_id == null
    error_message = "The hub's own catalog and policy are already its own: nothing more to bind."
  }
}

run "not_served" {
  command = plan
  variables { workspace = "not-served" }

  assert {
    condition     = !contains(keys(local.catalog_grants), "11111111-1111-1111-1111-111111111111")
    error_message = "self_service: false: no catalog grants for the apps."
  }
  assert {
    condition     = length(local.serverless_policies.self_service.principals) == 0 && !output.self_service.enabled
    error_message = "self_service: false: the usage policy keeps its groups only."
  }
  assert {
    condition     = length(databricks_workspace_binding.self_service_hub) == 0
    error_message = "self_service: false: its catalog is not bound to the hub."
  }
}

run "before_the_first_deploy" {
  command = plan
  variables {
    workspace        = "basic"
    self_service_dir = "tests/self-service-empty"
  }

  assert {
    condition     = length(local.self_service_app_ids) == 0 && !contains(keys(local.catalog_grants), "11111111-1111-1111-1111-111111111111")
    error_message = "No app_ids yet: nothing is granted."
  }
  assert {
    condition     = length(databricks_workspace_binding.self_service_hub) == 0 && local.self_service_hub_id == null
    error_message = "No hub yet (hub.host empty): nothing is bound to it."
  }
}
