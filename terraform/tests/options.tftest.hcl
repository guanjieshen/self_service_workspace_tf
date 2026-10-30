# Workspace options: fixtures/full sets every option, fixtures/unmanaged leaves every setting alone.
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

run "access" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = jsonencode(local.token_groups) == jsonencode(["tst-builders"])
    error_message = "personas.<persona>.can_create_tokens changes who may create tokens (here builders only)."
  }
  assert {
    condition     = local.extra_groups == tolist(["tst_users"])
    error_message = "The users group is assigned to the workspace."
  }
}

run "tags" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = local.chargeback_tags == { BUSINESS_UNIT = "TST", APP_ID = "TST-APP", COST_CENTER = "CC-42" }
    error_message = "A workspace's tags: change a value, add a tag, and null drops one (COST_CATEGORY). Got: ${jsonencode(local.chargeback_tags)}"
  }
  assert {
    condition     = local.serverless_policies.self_service.tags == local.chargeback_tags
    error_message = "The usage policy carries the workspace's tags."
  }
}

run "compute_options" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = local.config.sql_warehouse.size == "Medium" && local.config.sql_warehouse.max_clusters == 4 && local.config.sql_warehouse.min_clusters == 1
    error_message = "sql_warehouse in a workspace's file overrides only the keys it sets."
  }
  assert {
    condition     = local.config.cluster_policy.max_workers == 8 && local.config.cluster_policy.jobs.max_clusters_per_user == 1 && local.config.cluster_policy.pipelines == null
    error_message = "cluster_policy.max_workers overrides that limit only; pipelines: null means no pipelines policy."
  }
  assert {
    condition     = contains(output.released_addresses, "module.compute.databricks_cluster_policy.classic[\"pipelines\"]") && !contains(output.released_addresses, "module.compute.databricks_cluster_policy.classic[\"jobs\"]")
    error_message = "A policy kind set to null is released (left in the workspace), never deleted, like any setting."
  }
}

run "catalog_and_settings" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = length(module.catalog) == 1 && local.catalog.name == "tst_citizen_dev"
    error_message = "catalog.yaml names the catalog."
  }
  assert {
    condition     = local.default_catalog == "tst_citizen_dev"
    error_message = "default_catalog is passed to the default namespace setting."
  }
  assert {
    condition     = tolist(local.settings.dashboard_embedding.approved_domains) == tolist(["contoso.sharepoint.com"])
    error_message = "settings.dashboard_embedding.approved_domains sets the approved embedding domains."
  }
  assert {
    condition     = local.settings.disable_legacy_access == true
    error_message = "Keys a workspace does not set keep the baseline value."
  }
}

run "genie_code_workspace_parts" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = strcontains(local.genie_instructions, "# Default instructions") && strcontains(local.genie_instructions, "# Workspace instructions\n\nFor this workspace only, in addition to the default instructions.")
    error_message = "Default and workspace instructions each get their heading, default first."
  }
  assert {
    condition     = strcontains(local.genie_instructions, "Use the TST warehouse TST Default Warehouse and the catalog tst_citizen_dev; tags `APP_ID` = `TST-APP`, `BUSINESS_UNIT` = `TST`, `COST_CENTER` = `CC-42`.")
    error_message = "Placeholders in the workspace instructions are filled ({BU}, {WAREHOUSE}, {CATALOG}, {WORKSPACE_TAGS})."
  }
  assert {
    condition     = !strcontains(local.genie_instructions, "must not be deployed")
    error_message = "Comments are removed from the workspace instructions."
  }
}

run "settings_left_alone" {
  command = plan
  variables { workspace = "unmanaged" }

  assert {
    condition = alltrue([for k in [
      "disable_legacy_access", "disable_dbfs_root_and_mounts", "enforce_user_isolation", "restrict_workspace_admins",
      "personal_access_tokens", "data_handling", "git", "dashboard_embedding", "sql", "users_group_entitlements",
      "compliance_security_profile", "enhanced_security_monitoring", "automatic_cluster_update", "verbose_audit_logs",
      "enforce_unity_gateway", "collaboration_platforms",
    ] : local.settings[k] == null])
    error_message = "Every setting set to null is left alone."
  }
  assert {
    condition     = local.config.catalog == null && local.catalog == null && length(module.catalog) == 0 && contains(output.released_addresses, "module.catalog")
    error_message = "catalog: null (a whole section) means no catalog managed (the baseline is not used instead), and an existing one is released, not deleted."
  }
  assert {
    condition     = length(module.budget_policies) == 0 && length(data.databricks_sql_warehouses.starter) == 0
    error_message = "serverless_policy.enabled: false stops managing the usage policy; starter_warehouse.admins_only: null does not even look the warehouse up."
  }
  assert {
    condition     = !local.manage_genie_instructions && !local.manage_genie_skills
    error_message = "settings.genie_code: null leaves the instructions and skills alone."
  }
  assert {
    condition = alltrue([for a in [
      "module.budget_policies",
      "module.compute.databricks_permissions.starter_warehouse",
      "module.personas.databricks_entitlements.users",
      "module.workspace_settings.databricks_disable_legacy_access_setting.this",
      "module.workspace_settings.databricks_workspace_conf.key[\"enableTokensConfig\"]",
      "module.workspace_settings.databricks_workspace_conf.key[\"enforceUserIsolation\"]",
      "module.workspace_settings.databricks_workspace_file.genie_code_instructions",
      "module.workspace_settings.databricks_workspace_file.genie_code_skills",
    ] : contains(output.released_addresses, a)])
    error_message = "Every setting left alone is released (removed from the state on apply), not destroyed. Got: ${jsonencode(output.released_addresses)}"
  }
}

run "one_subkey_left_alone" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = local.settings.data_handling.notebook_export == null && local.settings.data_handling.results_download == true
    error_message = "One key of a map can be set to null; the others keep the baseline."
  }
  assert {
    condition     = contains(output.released_addresses, "module.workspace_settings.databricks_workspace_conf.key[\"enableExportNotebook\"]") && !contains(output.released_addresses, "module.workspace_settings.databricks_workspace_conf.key[\"enableResultsDownloading\"]")
    error_message = "Only the key set to null is released."
  }
}

run "all_settings_left_alone" {
  command = plan
  variables { workspace = "settings-null" }

  assert {
    condition     = alltrue([for k, v in local.settings : v == null]) && contains(output.released_addresses, "module.workspace_settings.databricks_disable_legacy_access_setting.this")
    error_message = "settings: null leaves every admin setting alone (each one released)."
  }
}

# A workspace that names only some persona groups: the others are skipped, nothing fails.
run "some_groups" {
  command = plan
  variables { workspace = "some-groups" }

  assert {
    condition     = tolist(keys(local.persona_groups)) == tolist(["explorer"])
    error_message = "Only the personas with a group are granted. Got: ${jsonencode(local.persona_groups)}"
  }
  assert {
    condition     = local.users_group == null && !contains(keys(local.entitlement_groups), "users")
    error_message = "No users group: no users entitlements. Got: ${jsonencode(local.users_group)}"
  }
  assert {
    condition     = local.platform_admins == tolist(["tst_platform_admins"])
    error_message = "The platform admins group comes from the baseline: {bu}_platform_admins."
  }
  assert {
    condition     = local.serverless_policies.self_service.groups == tolist(["tst-explorers", "tst_platform_admins"])
    error_message = "The usage policy goes to the personas that have a group, and the platform admins."
  }
}

