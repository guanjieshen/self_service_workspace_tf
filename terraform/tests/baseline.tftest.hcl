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
    condition     = local.bu == "tst" && local.bu_upper == "TST" && local.workspace_tags == { LOB = "TESTLOB" }
    error_message = "bu and the workspace's tags come from its file."
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
    condition     = local.config.sql_warehouse.tags == { DEPARTMENT = "SHARED", TEAM = "SHARED" }
    error_message = "Shared compute is tagged DEPARTMENT and TEAM SHARED (LOB is added by the module)."
  }
  assert {
    condition     = local.config.classic_warehouse.enabled == false && local.config.shared_cluster.enabled == true
    error_message = "Classic warehouse off, shared cluster on by default."
  }
  assert {
    condition     = can(regex("^[0-9]+\\.[0-9x]+(\\.x)?-scala[0-9.]+$", local.config.shared_cluster.runtime))
    error_message = "The shared cluster's runtime is a pinned version, not latest_lts: a new LTS would restart it on an unrelated apply."
  }
  assert {
    condition     = tolist(local.config.required_tags) == tolist(["LOB", "DEPARTMENT", "TEAM"])
    error_message = "Required tags are LOB, DEPARTMENT and TEAM."
  }
}

run "personas" {
  command = plan

  assert {
    condition     = jsonencode(local.persona_groups) == jsonencode({ builder = ["tst-builders"], explorer = ["tst-explorers"], publisher = ["tst-publishers"] }) && jsonencode(local.platform_admins) == jsonencode(["tst-admins"])
    error_message = "One group per persona, from groups in access.yaml."
  }
  assert {
    condition     = sort(keys(local.cluster_policies)) == tolist(["builder", "publisher"])
    error_message = "Only personas with cluster_policy: true (builder, publisher) get a cluster policy."
  }
  assert {
    condition     = local.cluster_policies.builder.name == "TST Builder Compute" && jsonencode(local.cluster_policies.builder.groups) == jsonencode(["tst-builders"]) && local.cluster_policies.publisher.tags == { PERSONA = "PUBLISHER" }
    error_message = "Cluster policies are named {BU} {PERSONA} Compute, granted to the persona's group and tagged with the persona."
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
    condition     = local.persona_acl.shared_cluster == { "tst-builders" = "CAN_ATTACH_TO", "tst-publishers" = "CAN_ATTACH_TO" }
    error_message = "Explorers get nothing on the shared cluster; builders and publishers can attach to it, not restart it."
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

run "serverless_usage_policies" {
  command = plan

  assert {
    condition     = sort(keys(local.budget_policies)) == tolist(["platform", "shared"])
    error_message = "Without teams there are two usage policies: shared and platform."
  }
  assert {
    condition     = local.budget_policies.shared.name == "TST-SHARED" && local.budget_policies.platform.name == "TST-PLATFORM"
    error_message = "Usage policies are named {BU}-SHARED and {BU}-PLATFORM."
  }
  assert {
    condition     = local.budget_policies.shared.tags == { LOB = "TESTLOB", DEPARTMENT = "SHARED", TEAM = "SHARED" }
    error_message = "The shared usage policy carries LOB and the shared tags."
  }
  assert {
    condition     = sort(local.budget_policies.shared.groups) == tolist(["tst-builders", "tst-explorers", "tst-publishers"]) && local.budget_policies.platform.groups == tolist(["tst-admins"])
    error_message = "Every persona may use the shared policy; platform admins the platform one."
  }
  assert {
    condition     = local.budget_policy_managers == tolist(["groups/tst-admins"])
    error_message = "Platform admins manage the usage policies."
  }
  assert {
    condition     = length(module.budget_policies) == 1
    error_message = "Usage policies are managed by default."
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
    condition     = !strcontains(local.genie_instructions, "<!--") && length(regexall("\\{(BU|LOB|CATALOG|WAREHOUSE)\\}", local.genie_instructions)) == 0
    error_message = "Comments are removed and placeholders filled."
  }
  assert {
    condition     = tolist(keys(local.genie_skills)) == tolist(["build-tagged-assets/SKILL.md"])
    error_message = "Every workspace inherits the default skills (and only skill folders, not the README). Got: ${jsonencode(keys(local.genie_skills))}"
  }
  assert {
    condition = (
      length(regexall("\\{(BU|LOB|CATALOG|WAREHOUSE)\\}", base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]))) == 0 &&
      strcontains(base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]), "TST Default Warehouse")
    )
    error_message = "Placeholders in skills are filled ({WAREHOUSE} = the default warehouse's name)."
  }
  assert {
    condition     = strcontains(base64decode(local.genie_skills["build-tagged-assets/SKILL.md"]), "`LOB`, `DEPARTMENT`, `TEAM`")
    error_message = "{TAGS} in a skill is the required tags."
  }
}
