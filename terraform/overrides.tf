# How a workspace changes the baseline.
#
# config/workspaces/<name>.yaml may set any top-level key of config/defaults/, with the same
# name and shape (config.tf merges them). A key set to null means "Terraform leaves
# this alone": on a workspace that was already applied, scripts/tf.sh then removes what the
# setting owns from the state ("release") instead of destroying it, because destroying a
# setting resets it.

locals {
  # Every baseline section the workspace file sets.
  overrides = { for s in local.defaults_sections : s => local.ws_all[s] if contains(keys(local.ws_all), s) }

  # Override paths the baseline does not have (usually a typo), two levels deep, and three
  # for map values. Open maps take any keys: tags (a workspace may add a tag), and maps
  # that are empty in the baseline.
  unknown_overrides = flatten([
    for s, o in local.overrides : can(keys(o)) && can(keys(local.defaults[s])) && s != "tags" ? flatten([
      for k in keys(o) : !contains(keys(local.defaults[s]), k) ? ["${s}.${k}"] : (
        can(keys(o[k])) && can(keys(local.defaults[s][k])) && length(try(keys(local.defaults[s][k]), [])) > 0 ?
        [for k2 in keys(o[k]) : "${s}.${k}.${k2}" if !contains(keys(local.defaults[s][k]), k2)] : []
      )
    ]) : []
  ])

  # ---- What a setting owns in the state ----
  # Released when the setting is null. scripts/tests/ checks that each address exists and
  # that every workspace configuration key the module sets is here.
  ws  = "module.workspace_settings"
  wsc = "module.workspace_settings.databricks_workspace_conf.key"
  setting_addresses = {
    "settings.disable_legacy_access"                              = ["${local.ws}.databricks_disable_legacy_access_setting.this"]
    "settings.disable_dbfs_root_and_mounts"                       = ["${local.ws}.databricks_disable_legacy_dbfs_setting.this"]
    "settings.enforce_user_isolation"                             = ["${local.wsc}[\"enforceUserIsolation\"]"]
    "settings.compliance_security_profile"                        = ["${local.ws}.databricks_compliance_security_profile_workspace_setting.this"]
    "settings.restrict_workspace_admins"                          = ["${local.ws}.databricks_restrict_workspace_admins_setting.this"]
    "settings.personal_access_tokens"                             = ["${local.wsc}[\"enableTokensConfig\"]", "${local.wsc}[\"maxTokenLifetimeDays\"]"]
    "settings.personal_access_tokens.enabled"                     = ["${local.wsc}[\"enableTokensConfig\"]"]
    "settings.personal_access_tokens.max_lifetime_days"           = ["${local.wsc}[\"maxTokenLifetimeDays\"]"]
    "settings.enhanced_security_monitoring"                       = ["${local.ws}.databricks_enhanced_security_monitoring_workspace_setting.this"]
    "settings.automatic_cluster_update"                           = ["${local.ws}.databricks_automatic_cluster_update_workspace_setting.this"]
    "settings.verbose_audit_logs"                                 = ["${local.wsc}[\"enableVerboseAuditLogs\"]"]
    "settings.enforce_unity_gateway"                              = ["${local.ws}.databricks_workspace_setting_v2.enforce_unity_gateway"]
    "settings.data_handling.results_download"                     = ["${local.wsc}[\"enableResultsDownloading\"]"]
    "settings.data_handling.sql_results_download"                 = ["${local.ws}.databricks_workspace_setting_v2.sql_results_download"]
    "settings.data_handling.mlflow_artifact_download"             = ["${local.wsc}[\"mlflowRunArtifactDownloadEnabled\"]"]
    "settings.data_handling.upload_data_ui"                       = ["${local.wsc}[\"enableUploadDataUis\"]"]
    "settings.data_handling.notebook_export"                      = ["${local.wsc}[\"enableExportNotebook\"]"]
    "settings.data_handling.notebook_table_clipboard"             = ["${local.wsc}[\"enableNotebookTableClipboard\"]"]
    "settings.data_handling.web_terminal"                         = ["${local.wsc}[\"enableWebTerminal\"]"]
    "settings.data_handling.dbfs_file_browser"                    = ["${local.wsc}[\"enableDbfsFileBrowser\"]"]
    "settings.data_handling.notebook_results_in_customer_storage" = ["${local.wsc}[\"storeInteractiveNotebookResultsInCustomerAccount\"]"]
    "settings.collaboration_platforms.allowed"                    = ["${local.ws}.databricks_workspace_setting_v2.collaboration_connectivity"]
    "settings.collaboration_platforms.public_messages"            = ["${local.ws}.databricks_workspace_setting_v2.collaboration_public_messages"]
    "settings.git"                                                = ["${local.wsc}[\"enableProjectsAllowList\"]", "${local.wsc}[\"projectsAllowList\"]"]
    "settings.git.restrict_to_allowlist"                          = ["${local.wsc}[\"enableProjectsAllowList\"]", "${local.wsc}[\"projectsAllowList\"]"]
    "settings.dashboard_embedding"                                = ["${local.ws}.databricks_aibi_dashboard_embedding_access_policy_setting.this", "${local.ws}.databricks_aibi_dashboard_embedding_approved_domains_setting.this"]
    "settings.sql"                                                = ["${local.ws}.databricks_sql_global_config.this"]
    "settings.users_group_entitlements"                           = ["module.personas.databricks_entitlements.users"]
    "settings.genie_code"                                         = ["${local.ws}.databricks_workspace_file.genie_code_instructions", "${local.ws}.databricks_workspace_file.genie_code_skills"]
    "settings.genie_code.instructions"                            = ["${local.ws}.databricks_workspace_file.genie_code_instructions"]
    "settings.genie_code.skills"                                  = ["${local.ws}.databricks_workspace_file.genie_code_skills"]
    "starter_warehouse.admins_only"                               = ["module.compute.databricks_permissions.starter_warehouse"]
    "cluster_policy.interactive"                                  = ["module.compute.databricks_cluster_policy.classic[\"interactive\"]"]
    "cluster_policy.jobs"                                         = ["module.compute.databricks_cluster_policy.classic[\"jobs\"]"]
    "cluster_policy.pipelines"                                    = ["module.compute.databricks_cluster_policy.classic[\"pipelines\"]"]
  }
  # Released when false (or null): serverless_policy.enabled.
  switch_addresses = {
    "serverless_policy.enabled" = ["module.budget_policies"]
  }

  setting_is_null = {
    for path in keys(local.setting_addresses) : path => (
      length(split(".", path)) == 2
      ? try(local.config[split(".", path)[0]][split(".", path)[1]], null) == null
      : try(local.config[split(".", path)[0]][split(".", path)[1]][split(".", path)[2]], null) == null
    )
  }
  switch_on = {
    for path in keys(local.switch_addresses) : path => try(local.config[split(".", path)[0]][split(".", path)[1]], null) == true
  }

  released_addresses = sort(distinct(flatten(concat(
    [for path, addrs in local.setting_addresses : addrs if local.setting_is_null[path]],
    [for path, addrs in local.switch_addresses : addrs if !local.switch_on[path]],
    # catalog: null leaves the catalog alone: released, never deleted (it holds data).
    local.catalog == null ? ["module.catalog"] : [],
  ))))

  # Sections a workspace may set to null as a whole; the others have keys to set to null instead.
  nullable_sections = ["settings", "catalog", "default_catalog"]
  null_sections     = [for s, v in local.overrides : s if v == null && !contains(local.nullable_sections, s)]
}
