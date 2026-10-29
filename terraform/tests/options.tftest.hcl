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
    error_message = "personas.<persona>.can_create_tokens in access.yaml changes who may create tokens (here builders only)."
  }
  assert {
    condition     = contains(local.extra_groups, "tst-data-eng") && contains(local.extra_groups, "tst_users")
    error_message = "Team groups and the users group are assigned to the workspace."
  }
  assert {
    condition     = contains(local.budget_policy_managers, "users/owner@example.com")
    error_message = "budget_policies.extra_managers in a workspace cost.yaml adds managers next to the platform admins."
  }
  assert {
    condition     = sort(keys(local.budget_policies)) == tolist(["builders", "platform", "shared"])
    error_message = "A workspace's cost.yaml adds policy blocks to the baseline's."
  }
  assert {
    condition     = local.budget_policies.platform.name == "TST-ADMIN" && local.budget_policies.platform.tags == { LOB = "TESTLOB", DEPARTMENT = "IT", TEAM = "PLATFORM" }
    error_message = "A block repeated in a workspace's cost.yaml replaces the baseline's (name and tags)."
  }
  assert {
    condition     = sort(local.budget_policies.builders.groups) == tolist(["tst-builders", "tst-publishers"]) && local.budget_policies.builders.name == "TST-BUILDERS"
    error_message = "used_by can list personas: the policy goes to their groups."
  }
}

run "teams" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = !contains(keys(local.budget_policies), "data-eng")
    error_message = "Teams get no usage policy of their own: only the blocks in cost.yaml are policies."
  }
  assert {
    condition     = contains(local.allowed_tag_values.TEAM, "DATA-ENG") && contains(local.allowed_tag_values.TEAM, "SHARED") && contains(local.allowed_tag_values.DEPARTMENT, "FINANCE")
    error_message = "Cluster policies allow the tag values of shared compute and teams."
  }
  assert {
    condition     = local.team_warehouse_inputs["data-eng"].group == "tst-data-eng" && local.team_warehouse_inputs["data-eng"].warehouse.size == "X-Small"
    error_message = "A team warehouse is defined in full in compute.yaml and granted to the team's group."
  }
}

run "compute_options" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = local.config.sql_warehouse.size == "Medium" && local.config.sql_warehouse.max_clusters == 4 && local.config.sql_warehouse.min_clusters == 1
    error_message = "compute.yaml warehouse overrides only the keys it sets."
  }
  assert {
    condition     = local.config.classic_warehouse.enabled == true && local.config.classic_warehouse.size == "Small"
    error_message = "classic_warehouse.enabled turns on the classic warehouse with the baseline size."
  }
  assert {
    condition     = local.config.shared_cluster.node_type == "Standard_E16_v3" && local.config.shared_cluster.single_node == true
    error_message = "shared_cluster.node_type overrides the node type only."
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
    error_message = "settings.dashboard_embedding.approved_domains in settings.yaml sets the approved embedding domains."
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
    condition     = strcontains(local.genie_instructions, "Use the TST warehouse TST Default Warehouse and the catalog tst_citizen_dev for TESTLOB.")
    error_message = "Placeholders in the workspace instructions are filled ({BU}, {WAREHOUSE}, {CATALOG}, {LOB})."
  }
  assert {
    condition     = !strcontains(local.genie_instructions, "must not be deployed")
    error_message = "Comments are removed from the workspace instructions."
  }
  assert {
    condition     = tolist(sort(keys(local.genie_skills))) == tolist(["build-tagged-assets/SKILL.md", "team-howto/SKILL.md", "team-howto/notes.txt"])
    error_message = "The workspace's own skills are deployed next to the default ones, with every file in the skill folder."
  }
  assert {
    condition     = base64decode(local.genie_skills["team-howto/SKILL.md"]) == "---\nname: team-howto\ndescription: Test skill. Use when asked how the TST team works.\n---\n\nAsk in the TST channel.\n"
    error_message = "Skill markdown has comments removed and placeholders filled."
  }
  assert {
    condition     = base64decode(local.genie_skills["team-howto/notes.txt"]) == "not markdown, deployed as is\n"
    error_message = "Other files in a skill folder are deployed unchanged."
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
    error_message = "Every setting set to null in settings.yaml is left alone."
  }
  assert {
    condition     = local.config.catalog == null && local.catalog == null && length(module.catalog) == 0 && contains(output.released_addresses, "module.catalog")
    error_message = "catalog: null (a whole section) means no catalog managed (the baseline is not used instead), and an existing one is released, not deleted."
  }
  assert {
    condition     = length(module.budget_policies) == 0
    error_message = "budget_policies.enabled: false in cost.yaml stops managing usage policies."
  }
  assert {
    condition     = !local.manage_genie_instructions && !local.manage_genie_skills
    error_message = "settings.genie_code: null leaves the instructions and skills alone."
  }
  assert {
    condition = alltrue([for a in [
      "module.budget_policies",
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
    condition     = length(local.cluster_policies) == 0 && local.budget_policies.shared.groups == tolist(["tst-explorers"])
    error_message = "No builder or publisher group: no cluster policies; the shared usage policy goes to the explorers only."
  }
}

