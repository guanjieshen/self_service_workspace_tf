# The central target (config/central.yaml): the cost dashboard, its view and who sees what.
# Fixture workspaces: hub (the central workspace) and fin.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  workspaces_dir = "tests/fixtures/workspaces"
  defaults_dir   = "tests/fixtures/defaults"
  # What the account lookup returns: only the policies bound to a managed workspace.
  policy_names = { "p-hub" = "HUB-0-SELF-SERVICE", "p-fin" = "FIN-0-SELF-SERVICE" }
}

run "who_sees_what" {
  command = plan
  variables { config_dir = "tests/fixtures/on" }

  assert {
    condition = toset([for a in local.access : "${a.workspace_id}=${a.group}"]) == toset([
      "1111111111111111=hub-explorers", "1111111111111111=hub-users", "1111111111111111=hub_platform_admins",
      "2222222222222222=fin-builders", "2222222222222222=fin-users", "2222222222222222=fin_platform_admins",
    ])
    error_message = "Each workspace's persona groups and platform admins (named as the baseline names them) see its rows; templates are skipped. Got: ${jsonencode(local.access)}"
  }
  assert {
    condition     = local.external_groups == tolist(["fin-builders", "fin-users", "fin_platform_admins"])
    error_message = "Only the other workspaces' groups get consumer access to the central workspace; its own groups are its baseline's."
  }
}

run "the_view_filters_rows_and_applies_the_discount" {
  command = plan
  variables { config_dir = "tests/fixtures/on" }

  assert {
    condition = alltrue([
      strcontains(local.view_sql, "is_account_group_member(a.group_name)"),
      strcontains(local.view_sql, "(1 - 15 / 100)"),
      strcontains(local.view_sql, "('2222222222222222', 'fin_platform_admins')"),
      strcontains(local.view_sql, "('p-fin', 'FIN-0-SELF-SERVICE')"),
    ])
    error_message = "The view keeps a viewer to their workspaces' rows, and its cost is list price less the discount."
  }
  assert {
    condition     = databricks_sql_table.usage_cost[0].table_type == "VIEW" && databricks_sql_table.usage_cost[0].catalog_name == "hub_shared" && databricks_schema.cost[0].name == "cost"
    error_message = "The view is hub_shared.cost.usage_cost."
  }
  assert {
    condition     = databricks_dashboard.cost[0].embed_credentials == false && strcontains(databricks_dashboard.cost[0].serialized_dashboard, "hub_shared.cost.usage_cost") && strcontains(databricks_dashboard.cost[0].serialized_dashboard, "(15%)")
    error_message = "The dashboard reads the view with each viewer's credentials, and says which discount it applies."
  }
  assert {
    condition = (
      strcontains(local.view_sql, "u.identity_metadata.run_as LIKE '%@%'") &&
      strcontains(local.view_sql, "IN ('GENIE', 'JOBS', 'DLT'))) AS personal") &&
      strcontains(databricks_dashboard.cost[0].serialized_dashboard, "WHERE personal AND run_as = current_user()")
    )
    error_message = "My usage counts only what ran as the person: serverless notebooks, Genie, and their own jobs and pipelines."
  }
  assert {
    condition     = length(databricks_sql_endpoint.dashboard) == 1 && length(databricks_permissions.warehouse) == 1
    error_message = "Without warehouse_id, Terraform creates the dashboard's warehouse and lets the viewers use it."
  }
  assert {
    condition     = toset([for a in databricks_permissions.dashboard[0].access_control : "${a.group_name}=${a.permission_level}"]) == toset([for g in local.viewer_groups : "${g}=CAN_RUN"])
    error_message = "Every viewer group may run the dashboard."
  }
}

run "a_given_warehouse_is_used_as_it_is" {
  command = plan
  variables { config_dir = "tests/fixtures/given-warehouse" }

  assert {
    condition     = length(databricks_sql_endpoint.dashboard) == 0 && length(databricks_permissions.warehouse) == 0 && local.warehouse_id == "abc123" && databricks_dashboard.cost[0].warehouse_id == "abc123"
    error_message = "warehouse_id names the warehouse for the dashboard and the view; Terraform creates none and leaves its permissions alone."
  }
}

run "off_creates_nothing" {
  command = plan
  variables { config_dir = "tests/fixtures/off" }

  assert {
    condition     = length(databricks_dashboard.cost) == 0 && length(databricks_schema.cost) == 0 && length(databricks_sql_endpoint.dashboard) == 0 && length(databricks_grant.catalog) == 0
    error_message = "enabled: false creates nothing."
  }
}

run "the_discount_is_a_percentage" {
  command = plan
  variables { config_dir = "tests/fixtures/bad-discount" }
  expect_failures = [terraform_data.config_checks]
}

run "the_view_is_not_in_a_managed_catalog" {
  command = plan
  variables { config_dir = "tests/fixtures/managed-catalog" }
  expect_failures = [terraform_data.config_checks]
}
