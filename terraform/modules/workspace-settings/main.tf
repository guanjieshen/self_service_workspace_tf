locals {
  s   = var.settings
  pat = try(local.s.personal_access_tokens, null)
  dh  = try(local.s.data_handling, null)
  git = try(local.s.git, null)

  tokens_enabled = try(local.pat.enabled, null) == true

  # Workspace configuration keys; null values are left unmanaged.
  conf_candidates = {
    enforceUserIsolation                             = try(local.s.enforce_user_isolation, null)
    enableTokensConfig                               = try(local.pat.enabled, null)
    maxTokenLifetimeDays                             = local.tokens_enabled ? try(local.pat.max_lifetime_days, null) : null
    enableResultsDownloading                         = try(local.dh.results_download, null)
    enableExportNotebook                             = try(local.dh.notebook_export, null)
    enableNotebookTableClipboard                     = try(local.dh.notebook_table_clipboard, null)
    enableWebTerminal                                = try(local.dh.web_terminal, null)
    enableDbfsFileBrowser                            = try(local.dh.dbfs_file_browser, null)
    enableProjectsAllowList                          = try(local.git.restrict_to_allowlist, null)
    projectsAllowList                                = try(local.git.restrict_to_allowlist, false) == true ? join(",", local.git.allowed_urls) : null
    storeInteractiveNotebookResultsInCustomerAccount = try(local.dh.notebook_results_in_customer_storage, null)
    mlflowRunArtifactDownloadEnabled                 = try(local.dh.mlflow_artifact_download, null)
    enableUploadDataUis                              = try(local.dh.upload_data_ui, null)
    enableVerboseAuditLogs                           = try(local.s.verbose_audit_logs, null)
  }
  custom_config = { for k, v in local.conf_candidates : k => tostring(v) if v != null }

  token_groups = length(var.token_groups) > 0 ? var.token_groups : var.platform_admins

  embedding_policy = try(local.s.dashboard_embedding.policy, null)
  collab           = try(local.s.collaboration_platforms, null)
}

resource "databricks_default_namespace_setting" "this" {
  count = var.default_catalog != null ? 1 : 0
  namespace {
    value = var.default_catalog
  }
}

resource "databricks_disable_legacy_access_setting" "this" {
  count = try(local.s.disable_legacy_access, null) != null ? 1 : 0
  disable_legacy_access {
    value = local.s.disable_legacy_access
  }
}

resource "databricks_disable_legacy_dbfs_setting" "this" {
  count = try(local.s.disable_dbfs_root_and_mounts, null) != null ? 1 : 0
  disable_legacy_dbfs {
    value = local.s.disable_dbfs_root_and_mounts
  }
}

# Only managed when turned on: changing this setting (in either direction) requires
# an account admin, and ALLOW_ALL is the platform default anyway.
resource "databricks_restrict_workspace_admins_setting" "this" {
  count = try(local.s.restrict_workspace_admins, null) == true ? 1 : 0
  restrict_workspace_admins {
    status = "RESTRICT_TOKENS_AND_JOB_RUN_AS"
  }
}

resource "databricks_aibi_dashboard_embedding_access_policy_setting" "this" {
  count = local.embedding_policy != null ? 1 : 0
  aibi_dashboard_embedding_access_policy {
    access_policy_type = local.embedding_policy
  }
}

resource "databricks_aibi_dashboard_embedding_approved_domains_setting" "this" {
  count = local.embedding_policy == "ALLOW_APPROVED_DOMAINS" ? 1 : 0
  aibi_dashboard_embedding_approved_domains {
    approved_domains = local.s.dashboard_embedding.approved_domains
  }
  depends_on = [databricks_aibi_dashboard_embedding_access_policy_setting.this]
}

# One resource per workspace configuration key, so a key can stop being managed
# (set to null) by removing just its resource from the state. The provider erases
# a key that disappears from a resource: removing or destroying one resets that key
# (enable*/enforce* to "false"), which is why scripts/tf.sh releases instead.
resource "databricks_workspace_conf" "key" {
  for_each      = local.custom_config
  custom_config = { (each.key) = each.value }
}

# Who may create personal access tokens (admins always can).
resource "databricks_permissions" "tokens" {
  count         = local.tokens_enabled && length(local.token_groups) > 0 ? 1 : 0
  authorization = "tokens"

  dynamic "access_control" {
    for_each = toset(local.token_groups)
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
  depends_on = [databricks_workspace_conf.key]
}

# ONE-WAY: once enabled, the compliance security profile cannot be turned off.
resource "databricks_compliance_security_profile_workspace_setting" "this" {
  count = try(local.s.compliance_security_profile, null) != null ? 1 : 0
  compliance_security_profile_workspace {
    is_enabled           = true
    compliance_standards = local.s.compliance_security_profile
  }
}

resource "databricks_enhanced_security_monitoring_workspace_setting" "this" {
  count = try(local.s.enhanced_security_monitoring, null) != null ? 1 : 0
  enhanced_security_monitoring_workspace {
    is_enabled = local.s.enhanced_security_monitoring
  }
}

resource "databricks_automatic_cluster_update_workspace_setting" "this" {
  count = try(local.s.automatic_cluster_update, null) != null ? 1 : 0
  automatic_cluster_update_workspace {
    enabled = local.s.automatic_cluster_update
  }
}

# "Enforce Unity Gateway": foundation model traffic only through Unity Gateway.
resource "databricks_workspace_setting_v2" "enforce_unity_gateway" {
  count = try(local.s.enforce_unity_gateway, null) != null ? 1 : 0
  name  = "enforce_ai_gateway_v3_only"
  boolean_val = {
    value = local.s.enforce_unity_gateway
  }
}

# "SQL results download": downloads in the SQL editor and dashboards (notebook results are
# enableResultsDownloading above).
resource "databricks_workspace_setting_v2" "sql_results_download" {
  count = try(local.dh.sql_results_download, null) != null ? 1 : 0
  name  = "sql_results_download"
  boolean_val = {
    value = local.dh.sql_results_download
  }
}

# "Allowed collaboration platforms" (Slack, Microsoft Teams) and "Allow public messages".
resource "databricks_workspace_setting_v2" "collaboration_connectivity" {
  count = try(local.collab.allowed, null) != null ? 1 : 0
  name  = "collaboration_platform_connectivity"
  collaboration_platform_connectivity = {
    connectivity = local.collab.allowed
  }
}

resource "databricks_workspace_setting_v2" "collaboration_public_messages" {
  count = try(local.collab.public_messages, null) != null ? 1 : 0
  name  = "collaboration_platform_message_visibility"
  boolean_val = {
    value = local.collab.public_messages
  }
}

# "Workspace label": a label and color next to the workspace name in the top bar, so
# people can tell workspaces apart (for example DEV and PROD).
resource "databricks_workspace_setting_v2" "workspace_label" {
  count = var.workspace_label != null ? 1 : 0
  name  = "workspace_label"
  workspace_label = {
    label = var.workspace_label.text
    color = var.workspace_label.color
  }
  # Provider bug (1.137.0): effective_workspace_label is optional instead of computed, so the
  # value the API returns after apply "was null" in the plan and the apply fails. Setting it to
  # the same value keeps plan and result equal.
  effective_workspace_label = {
    label = var.workspace_label.text
    color = var.workspace_label.color
  }
}

resource "databricks_sql_global_config" "this" {
  count = try(local.s.sql.statement_timeout_seconds, null) != null ? 1 : 0
  sql_config_params = {
    STATEMENT_TIMEOUT = tostring(local.s.sql.statement_timeout_seconds)
  }
}

# Genie Code workspace instructions: a workspace file that only admins can edit.
# Genie Code gives it priority over each user's own instructions. Manual edits in
# the Genie Code settings are replaced on the next apply.
resource "databricks_workspace_file" "genie_code_instructions" {
  count          = var.genie_code_instructions != null ? 1 : 0
  path           = "/.assistant_workspace_instructions.md"
  content_base64 = base64encode("${var.genie_code_instructions}\n")
}

# Genie Code workspace skills: available to every user, loaded when a request
# matches a skill's description or someone @-mentions it. Only the files listed
# here are managed; skills that admins add by hand are left alone.
resource "databricks_workspace_file" "genie_code_skills" {
  for_each       = var.genie_code_skills
  path           = "/.assistant/skills/${each.key}"
  content_base64 = each.value
}
