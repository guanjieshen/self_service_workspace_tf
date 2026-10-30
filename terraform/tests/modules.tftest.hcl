# What the modules build from their inputs: names, tags, permissions and which resources exist.
# Each run calls one module directly, with small inputs written here.

mock_provider "databricks" {}

variables {
  workspace        = "basic"
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures"
  use_cli_profiles = false
}

run "compute" {
  command = plan
  module {
    source = "./modules/compute"
  }
  variables {
    names             = { BU = "TST", bu = "tst" }
    tags              = { BUSINESS_UNIT = "TST", APP_ID = "TST-APP", COST_CATEGORY = "CITIZEN_SELF_SERVICE" }
    classic_user_tags = ["APP_ID", "TEAM"]
    user_tag_pattern  = "^[A-Z0-9_-]+$"
    sql_warehouse = {
      name         = "{BU} Default Warehouse", type = "serverless", size = "Small",
      min_clusters = 1, max_clusters = 2, auto_stop_minutes = 5, workspace_default = true
    }
    cluster_policy = {
      runtime     = "lts_only", access_modes = ["STANDARD"], node_types = ["Standard_E8_v3", "Standard_E16_v3"], max_workers = 4
      interactive = { name = "{BU} Classic Interactive", max_clusters_per_user = 1, max_autotermination_minutes = 60 }
      jobs        = { name = "{BU} Classic Jobs", max_clusters_per_user = 1 }
      pipelines   = { name = "{BU} Classic Pipelines", max_clusters_per_user = 1 }
    }
    warehouse_acl     = { tst-explorers = "CAN_USE" }
    starter_warehouse = ["starter-id"]
    platform_admins   = ["tst-admins"]
  }

  assert {
    condition     = databricks_permissions.starter_warehouse["starter-id"].sql_endpoint_id == "starter-id" && toset([for a in databricks_permissions.starter_warehouse["starter-id"].access_control : "${a.group_name}=${a.permission_level}"]) == toset(["tst-admins=CAN_MANAGE"])
    error_message = "Only the platform admins may use the Serverless Starter Warehouse (everyone else's access goes)."
  }
  assert {
    condition     = databricks_workspace_setting_v2.default_warehouse[0].name == "default_warehouse_id"
    error_message = "workspace_default makes the default warehouse the workspace's Default warehouse."
  }
  assert {
    condition     = databricks_sql_endpoint.default.name == "TST Default Warehouse" && databricks_sql_endpoint.default.enable_serverless_compute
    error_message = "{BU} is filled in the warehouse name; type serverless makes it serverless."
  }
  assert {
    condition     = toset([for t in databricks_sql_endpoint.default.tags[0].custom_tags : "${t.key}=${t.value}"]) == toset(["BUSINESS_UNIT=TST", "APP_ID=TST-APP", "COST_CATEGORY=CITIZEN_SELF_SERVICE"])
    error_message = "The warehouse carries the chargeback tags."
  }
  assert {
    condition     = toset([for a in databricks_permissions.default_warehouse[0].access_control : "${a.group_name}=${a.permission_level}"]) == toset(["tst-explorers=CAN_USE", "tst-admins=CAN_MANAGE"])
    error_message = "Personas get their warehouse permission; platform admins Can manage."
  }
  assert {
    condition     = sort(keys(databricks_cluster_policy.classic)) == tolist(["interactive", "jobs", "pipelines"]) && databricks_cluster_policy.classic["jobs"].name == "TST Classic Jobs" && databricks_cluster_policy.classic["interactive"].max_clusters_per_user == 1
    error_message = "One classic cluster policy per kind, named from its input."
  }
  assert {
    condition = (
      jsondecode(databricks_cluster_policy.classic["interactive"].definition)["cluster_type"] == { type = "fixed", value = "all-purpose" } &&
      jsondecode(databricks_cluster_policy.classic["jobs"].definition)["cluster_type"] == { type = "fixed", value = "job" } &&
      jsondecode(databricks_cluster_policy.classic["pipelines"].definition)["cluster_type"] == { type = "fixed", value = "dlt" }
    )
    error_message = "Each policy is fixed to its kind of cluster, so an interactive cluster cannot use the jobs policy's allowance."
  }
  assert {
    condition = (
      contains(keys(jsondecode(databricks_cluster_policy.classic["interactive"].definition)), "autotermination_minutes") && !contains(keys(jsondecode(databricks_cluster_policy.classic["jobs"].definition)), "autotermination_minutes") &&
      contains(keys(jsondecode(databricks_cluster_policy.classic["jobs"].definition)), "spark_version") &&
      !contains(keys(jsondecode(databricks_cluster_policy.classic["pipelines"].definition)), "spark_version") && !contains(keys(jsondecode(databricks_cluster_policy.classic["pipelines"].definition)), "autotermination_minutes")
    )
    error_message = "Only interactive clusters get an auto-stop rule; pipelines get no runtime rule (pipeline compute rejects both)."
  }
  assert {
    condition = (
      jsondecode(databricks_cluster_policy.classic["jobs"].definition)["custom_tags.BUSINESS_UNIT"] == { type = "fixed", value = "TST" } &&
      jsondecode(databricks_cluster_policy.classic["jobs"].definition)["custom_tags.COST_CATEGORY"] == { type = "fixed", value = "CITIZEN_SELF_SERVICE" }
    )
    error_message = "The chargeback tags users do not fill in are fixed on every cluster."
  }
  assert {
    condition = (
      jsondecode(databricks_cluster_policy.classic["jobs"].definition)["custom_tags.APP_ID"] == { type = "regex", pattern = "^[A-Z0-9_-]+$", isOptional = false, defaultValue = "TST-APP" } &&
      jsondecode(databricks_cluster_policy.classic["jobs"].definition)["custom_tags.TEAM"] == { type = "regex", pattern = "^[A-Z0-9_-]+$", isOptional = false }
    )
    error_message = "Tags users fill in are required and must match the pattern; one with a chargeback value starts from it."
  }
  assert {
    condition     = jsondecode(databricks_cluster_policy.classic["jobs"].definition)["data_security_mode"].defaultValue == "USER_ISOLATION"
    error_message = "STANDARD access mode means shared (user isolation) clusters."
  }
}

run "compute_minimal" {
  command = plan
  module {
    source = "./modules/compute"
  }
  variables {
    names             = { BU = "TST", bu = "tst" }
    tags              = {}
    classic_user_tags = []
    user_tag_pattern  = "^[A-Z0-9_-]+$"
    sql_warehouse     = { name = "W", type = "serverless", size = "Small", min_clusters = 1, max_clusters = 1, auto_stop_minutes = 5 }
    cluster_policy = {
      runtime     = "any", access_modes = ["STANDARD"], node_types = ["Standard_E8_v3"], max_workers = 1
      interactive = { name = "I", max_clusters_per_user = 1, max_autotermination_minutes = 60 }
      jobs        = null
      pipelines   = null
    }
    warehouse_acl   = {}
    platform_admins = []
  }

  assert {
    condition     = length(databricks_workspace_setting_v2.default_warehouse) == 0 && length(databricks_permissions.default_warehouse) == 0 && length(databricks_permissions.starter_warehouse) == 0
    error_message = "Without workspace_default the Default warehouse setting is left alone; empty grants create no permissions."
  }
  assert {
    condition     = tolist(keys(databricks_cluster_policy.classic)) == tolist(["interactive"]) && length([for k in keys(jsondecode(databricks_cluster_policy.classic["interactive"].definition)) : k if startswith(k, "custom_tags.") || k == "spark_version"]) == 0
    error_message = "A kind set to null gets no policy; no tags means no tag rules; runtime any means no runtime rule."
  }
}

run "workspace_settings" {
  command = plan
  module {
    source = "./modules/workspace-settings"
  }
  variables {
    settings = {
      disable_legacy_access        = true
      disable_dbfs_root_and_mounts = null
      enforce_user_isolation       = true
      restrict_workspace_admins    = false
      personal_access_tokens       = { enabled = true, max_lifetime_days = 90 }
      data_handling                = { results_download = true, web_terminal = null, sql_results_download = false, upload_data_ui = false, mlflow_artifact_download = null }
      collaboration_platforms      = { allowed = "ALLOW_TEAMS", public_messages = false }
      git                          = { restrict_to_allowlist = true, allowed_urls = ["https://github.com/org/"] }
      dashboard_embedding          = { policy = "ALLOW_APPROVED_DOMAINS", approved_domains = ["contoso.sharepoint.com"] }
      sql                          = { statement_timeout_seconds = 14400 }
      enforce_unity_gateway        = true
      compliance_security_profile  = null
    }
    default_catalog         = "tst_cat"
    workspace_label         = { text = "DEV", color = "lime" }
    genie_code_instructions = "# Default instructions"
    genie_code_skills       = { "a/SKILL.md" = "eA==" }
    token_groups            = ["tst-publishers"]
    platform_admins         = ["tst-admins"]
  }

  assert {
    condition     = length(databricks_disable_legacy_access_setting.this) == 1 && length(databricks_disable_legacy_dbfs_setting.this) == 0
    error_message = "A setting that is null is left alone; true or false is managed."
  }
  assert {
    condition     = length(databricks_restrict_workspace_admins_setting.this) == 0
    error_message = "restrict_workspace_admins false is not managed (the setting is only turned on)."
  }
  assert {
    condition = { for k, r in databricks_workspace_conf.key : k => r.custom_config[k] } == {
      enforceUserIsolation     = "true", enableTokensConfig = "true", maxTokenLifetimeDays = "90",
      enableResultsDownloading = "true", enableProjectsAllowList = "true", projectsAllowList = "https://github.com/org/",
      enableUploadDataUis      = "false"
    }
    error_message = "Workspace configuration keys are set only for values that are not null."
  }
  assert {
    condition     = alltrue([for k, r in databricks_workspace_conf.key : length(r.custom_config) == 1])
    error_message = "One resource per key, so one key can be released (removed from the state) on its own."
  }
  assert {
    condition     = toset([for a in databricks_permissions.tokens[0].access_control : a.group_name]) == toset(["tst-publishers"])
    error_message = "Token permissions go to the token groups."
  }
  assert {
    condition     = tolist(databricks_aibi_dashboard_embedding_approved_domains_setting.this[0].aibi_dashboard_embedding_approved_domains[0].approved_domains) == tolist(["contoso.sharepoint.com"])
    error_message = "Approved embedding domains are set when the policy is ALLOW_APPROVED_DOMAINS."
  }
  assert {
    condition     = databricks_workspace_setting_v2.enforce_unity_gateway[0].name == "enforce_ai_gateway_v3_only" && databricks_workspace_setting_v2.enforce_unity_gateway[0].boolean_val.value
    error_message = "Enforce Unity Gateway is the enforce_ai_gateway_v3_only setting."
  }
  assert {
    condition     = databricks_workspace_setting_v2.sql_results_download[0].name == "sql_results_download" && databricks_workspace_setting_v2.sql_results_download[0].boolean_val.value == false
    error_message = "data_handling sql_results_download sets the SQL results download setting."
  }
  assert {
    condition     = databricks_workspace_setting_v2.collaboration_connectivity[0].collaboration_platform_connectivity.connectivity == "ALLOW_TEAMS" && databricks_workspace_setting_v2.collaboration_public_messages[0].name == "collaboration_platform_message_visibility" && databricks_workspace_setting_v2.collaboration_public_messages[0].boolean_val.value == false
    error_message = "collaboration_platforms sets the allowed platforms and message visibility."
  }
  assert {
    condition     = databricks_workspace_setting_v2.workspace_label[0].name == "workspace_label" && databricks_workspace_setting_v2.workspace_label[0].workspace_label.label == "DEV" && databricks_workspace_setting_v2.workspace_label[0].workspace_label.color == "lime"
    error_message = "label in the workspace's file sets the workspace_label setting (text and color)."
  }
  assert {
    condition     = databricks_workspace_setting_v2.workspace_label[0].effective_workspace_label == databricks_workspace_setting_v2.workspace_label[0].workspace_label
    error_message = "effective_workspace_label is set to the label too (provider bug workaround: otherwise the apply fails)."
  }
  assert {
    condition     = databricks_default_namespace_setting.this[0].namespace[0].value == "tst_cat"
    error_message = "default_catalog sets the default namespace."
  }
  assert {
    condition     = base64decode(databricks_workspace_file.genie_code_instructions[0].content_base64) == "# Default instructions\n" && databricks_workspace_file.genie_code_skills["a/SKILL.md"].path == "/.assistant/skills/a/SKILL.md"
    error_message = "Genie Code instructions and skills are deployed where Genie Code reads them."
  }
  assert {
    condition     = length(databricks_compliance_security_profile_workspace_setting.this) == 0
    error_message = "The compliance security profile is left alone when null."
  }
}

run "personas" {
  command = plan
  module {
    source = "./modules/personas"
  }
  variables {
    personas = {
      explorer  = { entitlements = { workspace_access = false, workspace_consume = true, databricks_sql_access = true, allow_cluster_create = false } }
      viewer    = { entitlements = { workspace_access = false, workspace_consume = true, databricks_sql_access = false, allow_cluster_create = false } }
      builder   = { entitlements = { workspace_access = true, workspace_consume = false, databricks_sql_access = true, allow_cluster_create = false } }
      publisher = { entitlements = { workspace_access = true, workspace_consume = false, databricks_sql_access = true, allow_cluster_create = false } }
    }
    persona_groups           = { explorer = ["tst-explorers", "tst-multi"], viewer = ["tst-viewers"], builder = ["tst-builders"], publisher = ["tst-publishers", "tst-multi"] }
    platform_admins          = ["tst-admins"]
    platform_admin_role      = "ADMIN"
    extra_groups             = []
    users_group_entitlements = { workspace_access = false, workspace_consume = false, databricks_sql_access = false, allow_cluster_create = false }
  }

  assert {
    condition     = databricks_entitlements.persona["tst-explorers"].databricks_sql_access == true && databricks_entitlements.persona["tst-explorers"].workspace_access == false && databricks_entitlements.persona["tst-explorers"].workspace_consume == null
    error_message = "Explorers get SQL access (which includes Databricks One), not the full workspace; consumer access is then not set (the provider rejects it with SQL access)."
  }
  assert {
    condition     = databricks_entitlements.persona["tst-viewers"].workspace_consume == true && databricks_entitlements.persona["tst-viewers"].workspace_access == null && databricks_entitlements.persona["tst-viewers"].databricks_sql_access == null
    error_message = "A consumer-only persona gets consumer access alone, with the other access entitlements unset."
  }
  assert {
    condition     = alltrue([for g in ["tst-builders", "tst-publishers"] : databricks_entitlements.persona[g].workspace_access == true && databricks_entitlements.persona[g].workspace_consume == null && databricks_entitlements.persona[g].databricks_sql_access])
    error_message = "Builders and publishers get full workspace access and SQL access."
  }
  assert {
    condition     = databricks_entitlements.persona["tst-multi"].workspace_access == true && databricks_entitlements.persona["tst-multi"].workspace_consume == null
    error_message = "A group that is explorer and publisher gets full workspace access (consumer access is then not needed)."
  }
  assert {
    condition     = alltrue([for g in ["tst-explorers", "tst-viewers", "tst-builders", "tst-publishers", "tst-multi"] : tolist(databricks_permission_assignment.this[g].permissions) == tolist(["USER"])]) && tolist(databricks_permission_assignment.this["tst-admins"].permissions) == tolist(["ADMIN"])
    error_message = "No persona group is workspace admin: persona groups are assigned as USER, only platform admins as ADMIN."
  }
  assert {
    condition     = databricks_entitlements.users[0].workspace_access == false && databricks_entitlements.users[0].workspace_consume == null && databricks_entitlements.users[0].databricks_sql_access == false
    error_message = "The users group grants nothing, so explorers are not given the full workspace through it."
  }
}

