# The baseline a workspace gets with only the required files (fixtures/basic).
# Plans against mocked providers: no workspace or credentials needed. Run from the repository root:
#   terraform -chdir=terraform init -backend=false && terraform -chdir=terraform test
# Root tests check what the configuration hands to each module; modules.tftest.hcl checks
# what the modules build from it.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures"
  use_cli_profiles = false
  workspace        = "basic"
}

run "names_and_tags" {
  command = plan

  assert {
    condition     = local.bu == "tst" && local.bu_upper == "TST" && local.chargeback_tags == { BUSINESS_UNIT = "TST", APP_ID = "TST-APP", COST_CATEGORY = "CITIZEN_SELF_SERVICE" }
    error_message = "The chargeback tags are the baseline's tags: with BUSINESS_UNIT from bu ({BU}) and the workspace's own APP_ID. Got: ${jsonencode(local.chargeback_tags)}"
  }
  assert {
    condition     = local.account_host == "https://accounts.azuredatabricks.net"
    error_message = "An Azure workspace uses the Azure account console (AWS and GCP hosts get theirs)."
  }
  assert {
    condition     = local.config.sql_warehouse.name == "{BU} Default Warehouse" && local.config.sql_warehouse.type == "serverless"
    error_message = "The default warehouse comes from the baseline."
  }
  assert {
    condition     = local.config.sql_warehouse.workspace_default == true
    error_message = "The default warehouse is also the workspace's Default warehouse for SQL."
  }
  assert {
    condition     = local.settings.data_handling.sql_results_download == true && local.settings.data_handling.upload_data_ui == true && local.settings.data_handling.mlflow_artifact_download == true && local.settings.collaboration_platforms.allowed == "ALLOW_TEAMS" && local.settings.collaboration_platforms.public_messages == null
    error_message = "SQL results download, UI uploads and MLflow artifact downloads are managed (on); collaboration platforms are limited to Microsoft Teams; public messages are left alone."
  }
  assert {
    condition     = tolist(local.classic_user_tags) == tolist(["APP_ID", "TEAM", "PROJECT"]) && local.all_tag_keys == tolist(["APP_ID", "BUSINESS_UNIT", "COST_CATEGORY", "TEAM", "PROJECT"])
    error_message = "Users fill in APP_ID, TEAM and PROJECT on classic clusters. Got: ${jsonencode(local.all_tag_keys)}"
  }
  assert {
    condition = (
      local.config.cluster_policy.interactive.name == "{BU} Classic Interactive" &&
      local.config.cluster_policy.jobs.name == "{BU} Classic Jobs" &&
      local.config.cluster_policy.pipelines.name == "{BU} Classic Pipelines" &&
      alltrue([for k in ["interactive", "jobs", "pipelines"] : local.config.cluster_policy[k].max_clusters_per_user == 1]) &&
      tolist(local.config.cluster_policy.access_modes) == tolist(["STANDARD"])
    )
    error_message = "Three classic cluster policies (interactive, jobs, pipelines), one cluster per person each, Standard access mode only."
  }
}

# The Starter warehouse Databricks creates in a new workspace: found by name, admins only.
run "starter_warehouse" {
  command = plan

  override_data {
    target = data.databricks_sql_warehouses.starter[0]
    values = { ids = ["starter-id"] }
  }

  assert {
    condition     = local.config.starter_warehouse.admins_only == true && data.databricks_sql_warehouses.starter[0].warehouse_name_contains == "Serverless Starter Warehouse"
    error_message = "The baseline restricts the Serverless Starter Warehouse to the platform admins, found by name."
  }
  assert {
    condition     = toset([for a in module.compute.starter_warehouse_permissions["starter-id"] : a]) == toset(["tst-admins=CAN_MANAGE"])
    error_message = "Only the platform admins may use it."
  }
}

run "personas" {
  command = plan

  assert {
    condition     = jsonencode(local.persona_groups) == jsonencode({ builder = ["tst-builders"], explorer = ["tst-explorers"], publisher = ["tst-publishers"] }) && jsonencode(local.platform_admins) == jsonencode(["tst-admins"])
    error_message = "One group per persona, from groups (baseline and the workspace's file)."
  }
  assert {
    condition     = !contains(keys(local.persona_acl), "bu_folder")
    error_message = "The BU folder has no persona permissions: /Workspace/Shared already gives everyone access."
  }
  assert {
    condition     = local.persona_acl.default_warehouse == { "tst-explorers" = "CAN_USE", "tst-builders" = "CAN_USE", "tst-publishers" = "CAN_USE" }
    error_message = "Every persona can use the default warehouse."
  }
  assert {
    condition     = alltrue([for p, d in local.config.personas : !contains(keys(d), "cluster_policy") && !contains(keys(d), "shared_cluster")])
    error_message = "No persona gets classic compute: access to the classic cluster policy comes from the self-service app."
  }
  assert {
    condition = (
      local.entitlement_personas.explorer.entitlements == local.access_tiers.sql &&
      local.entitlement_personas.builder.entitlements == local.access_tiers.workspace &&
      local.entitlement_personas.publisher.entitlements == local.access_tiers.workspace &&
      local.entitlement_personas.users.entitlements == local.access_tiers.consumer &&
      jsonencode(local.entitlement_groups.users) == jsonencode(["tst_users"]) &&
      alltrue([for p, d in local.access_tiers : !d.allow_cluster_create])
    )
    error_message = "Explorer SQL access; builder and publisher the full workspace; the users group (tst_users) Consumer access; nobody unrestricted cluster creation."
  }
  assert {
    condition     = local.config.personas.builder == local.config.personas.publisher
    error_message = "Builder and publisher are the same in this project."
  }
  assert {
    condition     = length(local.token_groups) == 0
    error_message = "No persona may create personal access tokens (platform admins only)."
  }
  assert {
    condition     = local.catalog_grants["tst-admins"] == tolist(["ALL_PRIVILEGES", "MANAGE"]) && alltrue([for p in ["tst-explorers", "tst-builders", "tst-publishers"] : local.catalog_grants[p] == tolist(["USE_CATALOG", "USE_SCHEMA"])])
    error_message = "On the catalog, personas get only USE CATALOG and USE SCHEMA (no data, no CREATE SCHEMA); platform admins everything."
  }
}

run "serverless_usage_policy" {
  command = plan

  assert {
    condition     = tolist(keys(local.serverless_policies)) == tolist(["self_service"]) && local.serverless_policies.self_service.name == "TST-0-SELF-SERVICE"
    error_message = "One usage policy per workspace, named {BU}-0-SELF-SERVICE (first alphabetically, so it is the fallback)."
  }
  assert {
    condition     = local.serverless_policies.self_service.tags == local.chargeback_tags
    error_message = "The usage policy carries the chargeback tags."
  }
  assert {
    condition     = sort(local.serverless_policies.self_service.groups) == tolist(["tst-admins", "tst-builders", "tst-explorers", "tst-publishers"])
    error_message = "Every persona and the platform admins may use it."
  }
  assert {
    condition     = length(module.budget_policies) == 1
    error_message = "The usage policy is managed by default."
  }
}

run "workspace_settings" {
  command = plan

  assert {
    condition     = local.settings.disable_legacy_access == true && local.settings.disable_dbfs_root_and_mounts == true && local.settings.enforce_user_isolation == true
    error_message = "Legacy access and DBFS root are disabled and user isolation enforced by default."
  }
  assert {
    condition     = local.settings.enforce_unity_gateway == true
    error_message = "Enforce Unity Gateway is on by default."
  }
  assert {
    condition     = local.settings.personal_access_tokens == { enabled = true, max_lifetime_days = 90 }
    error_message = "Tokens are allowed for at most 90 days."
  }
  assert {
    condition     = local.settings.sql.statement_timeout_seconds == 14400
    error_message = "SQL statements time out after 4 hours."
  }
  assert {
    condition     = length(module.catalog) == 1 && local.catalog.name == "tst_citizen_dev" && local.catalog.owner == "tst-admins" && local.default_catalog == null
    error_message = "Every workspace gets one catalog, {bu}_citizen_dev, owned by the platform admins group; no default catalog until set."
  }
  assert {
    condition = alltrue([
      for path, addrs in local.setting_addresses : local.setting_is_null[path] || length(setintersection(toset(addrs), toset(output.released_addresses))) == 0
    ]) && !contains(output.released_addresses, "module.workspace_settings.databricks_workspace_conf.key[\"enableTokensConfig\"]")
    error_message = "Only settings that are null are released; a managed setting never is."
  }
}

run "genie_code_defaults" {
  command = plan

  assert {
    condition     = startswith(local.genie_instructions, "# Default instructions\n\nShared by every citizen development workspace.")
    error_message = "The deployed instructions start with the default section."
  }
  assert {
    condition     = !strcontains(local.genie_instructions, "# Workspace instructions")
    error_message = "Without genie-code/instructions.md there is no workspace section."
  }
  assert {
    condition     = !strcontains(local.genie_instructions, "<!--") && length(regexall("\\{(BU|TAGS|WORKSPACE_TAGS|CATALOG|WAREHOUSE)\\}", local.genie_instructions)) == 0
    error_message = "Comments are removed and placeholders filled."
  }
  assert {
    condition     = tolist(keys(local.genie_skills)) == tolist(["build-tagged-assets/SKILL.md"])
    error_message = "Every workspace inherits the default skills (and only skill folders, not the README). Got: ${jsonencode(keys(local.genie_skills))}"
  }
  assert {
    condition = (
      length(regexall("\\{(BU|TAGS|WORKSPACE_TAGS|CATALOG|WAREHOUSE)\\}", base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]))) == 0 &&
      strcontains(base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]), "TST Default Warehouse")
    )
    error_message = "Placeholders in skills are filled ({WAREHOUSE} = the default warehouse's name)."
  }
  assert {
    condition     = strcontains(base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]), "`APP_ID`, `BUSINESS_UNIT`, `COST_CATEGORY`, `TEAM`, `PROJECT`")
    error_message = "{TAGS} in a skill is every chargeback tag."
  }
}
