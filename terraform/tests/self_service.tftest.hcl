# The self-service app's needs in a workspace it serves (terraform/self_service.tf):
# its service principals assigned and granted on the catalog, the jobs' identity on the usage
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
    condition     = toset(keys(databricks_permission_assignment.self_service_app)) == toset(["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"])
    error_message = "Both apps' service principals are assigned to a workspace the app serves."
  }
  assert {
    condition     = toset(keys(databricks_entitlements.self_service_app)) == toset(["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]) && alltrue([for e in databricks_entitlements.self_service_app : e.workspace_access])
    error_message = "Both apps get workspace access (the users group has none), so they can use the Jobs API."
  }
  assert {
    condition     = local.catalog_grants["11111111-1111-1111-1111-111111111111"] == tolist(["BROWSE", "USE_CATALOG"]) && local.catalog_grants["22222222-2222-2222-2222-222222222222"] == tolist(["BROWSE", "USE_CATALOG"])
    error_message = "The apps may see the catalog (USE CATALOG, BROWSE) and nothing more."
  }
  assert {
    condition     = local.serverless_policies.self_service.principals == tolist(["servicePrincipals/33333333-3333-3333-3333-333333333333"])
    error_message = "The identity running Terraform (which runs the self-service jobs) may use the usage policy."
  }
  assert {
    condition     = output.self_service.enabled && output.self_service.prefix == "tst" && output.self_service.id == "1111111111111111" && output.self_service.host == "https://adb-1111111111111111.1.azuredatabricks.net" && output.self_service.catalog == "tst_citizen_dev"
    error_message = "The output gives the app's deploy what this workspace's configuration already has."
  }
}

run "not_served" {
  command = plan
  variables { workspace = "not-served" }

  assert {
    condition     = length(databricks_permission_assignment.self_service_app) == 0 && length(databricks_entitlements.self_service_app) == 0 && !contains(keys(local.catalog_grants), "11111111-1111-1111-1111-111111111111")
    error_message = "self_service: false: no assignment and no catalog grants for the apps."
  }
  assert {
    condition     = length(local.serverless_policies.self_service.principals) == 0 && !output.self_service.enabled
    error_message = "self_service: false: the usage policy keeps its groups only."
  }
}

run "before_the_first_deploy" {
  command = plan
  variables {
    workspace        = "basic"
    self_service_dir = "tests/self-service-empty"
  }

  assert {
    condition     = length(databricks_permission_assignment.self_service_app) == 0 && length(local.self_service_app_ids) == 0
    error_message = "No app_ids yet: nothing is assigned or granted."
  }
}
