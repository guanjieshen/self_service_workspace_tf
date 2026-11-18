# Domains (terraform/domains.tf): fixtures/domains has two, on top of the workspace's own groups;
# fixtures/basic has none and must plan exactly as before.
# Lists are compared with tolist() on both sides: YAML lists are tuples, which never equal lists.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures"
  use_cli_profiles = false
}

run "domain_groups_are_persona_groups" {
  command = plan
  variables { workspace = "domains" }

  assert {
    condition     = tolist(local.persona_groups.explorer) == tolist(["tst-explorers", "tst-finance-explorers", "tst-finance-analysts", "tst-supply-explorers"])
    error_message = "A domain's groups join their persona after the workspace's own, with {prefix} filled in. Got: ${jsonencode(local.persona_groups)}"
  }
  assert {
    condition     = tolist(local.persona_groups.builder) == tolist(["tst-builders", "tst-finance-builders"])
    error_message = "A persona takes one group or a list. Got: ${jsonencode(local.persona_groups.builder)}"
  }
  assert {
    condition     = alltrue([for g in ["tst-finance-explorers", "tst-finance-analysts", "tst-finance-builders", "tst-supply-explorers"] : tolist(module.personas.assigned_groups[g]) == tolist(["USER"])])
    error_message = "Domain groups are assigned to the workspace as USER, like the persona groups."
  }
  assert {
    condition     = local.catalog_grants["tst-finance-builders"] == local.catalog_grants["tst-builders"] && local.warehouse_acl["tst-supply-explorers"] == local.warehouse_acl["tst-explorers"]
    error_message = "A domain group gets its persona's catalog privileges and the default (catch-all) warehouse's permission."
  }
}

run "each_domain_has_its_own_usage_policy" {
  command = plan
  variables { workspace = "domains" }

  assert {
    condition     = tolist(sort(keys(local.serverless_policies))) == tolist(["domain_finance", "domain_supply_chain", "self_service"])
    error_message = "The catch-all policy, and one per domain. Got: ${jsonencode(keys(local.serverless_policies))}"
  }
  assert {
    condition     = local.serverless_policies.domain_finance.name == "TST-0-DOMAIN-FINANCE" && local.serverless_policies.domain_supply_chain.name == "TST-0-DOMAIN-SUPPLY"
    error_message = "A domain's policy is {PREFIX}-0-DOMAIN-<NAME>, or the name it sets with {PREFIX} filled in."
  }
  assert {
    condition     = alltrue([for d in ["domain_finance", "domain_supply_chain"] : sort([local.serverless_policies[d].name, local.serverless_policies.self_service.name])[0] == local.serverless_policies[d].name])
    error_message = "A domain's policy sorts before the catch-all's, so its members' usage goes to it when they pick none."
  }
  assert {
    condition     = local.serverless_policies.domain_finance.tags == { BUSINESS_UNIT = "TST", APPID = "FIN-APP", DOMAIN = "FINANCE" }
    error_message = "A domain's tags: the workspace's, its own over them (APPID; null drops COST_CATEGORY), and DOMAIN. Got: ${jsonencode(local.serverless_policies.domain_finance.tags)}"
  }
  assert {
    condition     = local.serverless_policies.domain_supply_chain.tags.DOMAIN == "SUPPLY-CHAIN" && local.serverless_policies.domain_supply_chain.tags.COST_CATEGORY == "CITIZEN_SELF_SERVICE"
    error_message = "DOMAIN is the domain's name in upper case; tags it does not set are the workspace's."
  }
  assert {
    condition     = tolist(local.serverless_policies.domain_finance.groups) == tolist(["tst-finance-builders", "tst-finance-explorers", "tst-finance-analysts", "tst-admins"])
    error_message = "Only the domain's groups (and the platform admins) may use its policy. Got: ${jsonencode(local.serverless_policies.domain_finance.groups)}"
  }
  assert {
    condition     = contains(local.serverless_policies.self_service.groups, "tst-finance-explorers") && local.serverless_policies.self_service.tags.APPID == "TST-APP"
    error_message = "The catch-all policy keeps the workspace's APPID, and domain members may use it too."
  }
}

run "each_domain_has_its_own_warehouse" {
  command = plan
  variables { workspace = "domains" }

  assert {
    condition     = databricks_sql_endpoint.domain["finance"].name == "TST Finance Warehouse" && databricks_sql_endpoint.domain["finance"].cluster_size == "Small" && databricks_sql_endpoint.domain["finance"].max_num_clusters == 2
    error_message = "A domain's warehouse: {PREFIX} <Name> Warehouse, with its own keys over the baseline's."
  }
  assert {
    condition     = databricks_sql_endpoint.domain["supply_chain"].name == "TST Supply Chain Warehouse" && databricks_sql_endpoint.domain["supply_chain"].cluster_size == "Medium" && databricks_sql_endpoint.domain["supply_chain"].enable_serverless_compute
    error_message = "A domain that sets nothing gets the baseline's warehouse settings."
  }
  assert {
    condition     = { for t in databricks_sql_endpoint.domain["finance"].tags[0].custom_tags : t.key => t.value } == { BUSINESS_UNIT = "TST", APPID = "FIN-APP", DOMAIN = "FINANCE" }
    error_message = "A domain's warehouse carries the domain's tags."
  }
  assert {
    condition     = local.domain_warehouse_acl.finance == { "tst-finance-explorers" = "CAN_USE", "tst-finance-analysts" = "CAN_USE", "tst-finance-builders" = "CAN_USE", "tst-admins" = "CAN_MANAGE" }
    error_message = "The domain's groups may use its warehouse; the platform admins manage it. Got: ${jsonencode(local.domain_warehouse_acl.finance)}"
  }
  assert {
    condition     = length(databricks_permissions.domain_warehouse) == 2
    error_message = "Each domain's warehouse has its permissions."
  }
}

run "a_domain_may_have_its_own_folder" {
  command = plan
  variables { workspace = "domains" }

  assert {
    condition     = local.domain_folders == { finance = "/Workspace/Domains/Finance" } && length(databricks_directory.domain) == 1
    error_message = "Only a domain with folder: true gets a folder, /Workspace/Domains/<Name>. Got: ${jsonencode(local.domain_folders)}"
  }
  assert {
    condition     = local.domain_folder_acl.finance == { "tst-finance-explorers" = "CAN_READ", "tst-finance-analysts" = "CAN_READ", "tst-finance-builders" = "CAN_MANAGE", "tst-admins" = "CAN_MANAGE" }
    error_message = "The domain's groups only: read for a persona without workspace access, manage with it; the platform admins manage. Got: ${jsonencode(local.domain_folder_acl.finance)}"
  }
  assert {
    condition     = !contains(keys(local.domain_folder_acl.finance), "tst-explorers") && !contains(keys(local.domain_folder_acl.finance), "tst-builders")
    error_message = "The workspace's own persona groups get nothing on a domain's folder."
  }
  assert {
    condition     = databricks_directory.domain["finance"].delete_recursive == false && databricks_permissions.domain_folder["finance"].directory_path == "/Workspace/Domains/Finance"
    error_message = "A domain's folder is never deleted with what is in it, and its permissions are on that folder."
  }
}

run "a_workspace_without_domains_is_unchanged" {
  command = plan
  variables { workspace = "basic" }

  assert {
    condition     = length(databricks_sql_endpoint.domain) == 0 && length(databricks_permissions.domain_warehouse) == 0 && length(databricks_directory.domain) == 0
    error_message = "No domains: no domain warehouses or folders."
  }
  assert {
    condition     = tolist(keys(local.serverless_policies)) == tolist(["self_service"])
    error_message = "No domains: only the catch-all policy."
  }
  assert {
    condition     = alltrue([for p, gs in local.persona_groups : length(gs) == 1]) && tolist(local.persona_groups.explorer) == tolist(["tst-explorers"])
    error_message = "No domains: each persona has its one group, as before."
  }
}
