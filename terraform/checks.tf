# Validation: fails the plan with a plain-language message.

resource "terraform_data" "config_checks" {
  lifecycle {
    precondition {
      condition     = length(local.duplicate_settings) == 0
      error_message = "These settings are defined in more than one file in config/defaults/: ${join(", ", local.duplicate_settings)}."
    }
    precondition {
      condition     = length(local.null_sections) == 0
      error_message = "These sections cannot be null as a whole: ${join(", ", local.null_sections)}. Set the keys inside them to null to leave those alone (only settings, catalog and default_catalog can be null)."
    }
    precondition {
      condition     = length(local.unknown_overrides) == 0
      error_message = "These keys are not in the baseline (config/defaults/), so they change nothing; check the spelling: ${join(", ", local.unknown_overrides)}."
    }
    precondition {
      condition     = length(local.unknown_keys) == 0
      error_message = "The workspace file has keys that are neither a baseline setting nor a workspace key (usually a typo): ${join(", ", local.unknown_keys)}. Workspace keys: ${join(", ", local.workspace_keys)}; baseline settings: ${join(", ", sort(local.defaults_sections))}."
    }
    precondition {
      condition     = local.catalog == null || can(regex("^[a-z0-9_]+$", try(local.catalog.name, "")))
      error_message = "catalog.yaml catalog: the name must be lowercase letters, digits and underscores."
    }
    precondition {
      condition     = local.genie_instructions == null || length(coalesce(local.genie_instructions, "")) <= 19800
      error_message = "Genie Code instructions are ${length(coalesce(local.genie_instructions, ""))} characters (default plus workspace); Genie Code reads at most 20,000. Shorten genie_code_instructions or config/defaults/genie-code/instructions.md."
    }
    precondition {
      condition     = alltrue([for k, v in local.tag_values : can(regex("^[A-Za-z0-9_.-]+$", k)) && (v == null || can(tostring(v)))])
      error_message = "tags: each key must be letters, digits, _, . or - and each value a single value (or null to drop the tag)."
    }
    precondition {
      condition     = can(tolist(local.config.classic_user_tags)) && alltrue([for k, v in local.chargeback_tags : can(regex(local.user_tag_pattern, v)) if contains(local.classic_user_tags, k)])
      error_message = "classic_user_tags lists tags users fill in on a classic cluster, which must be upper case letters, digits, _ and -; a starting value under tags: must be too: ${join(", ", [for k, v in local.chargeback_tags : "${k} = ${v}" if contains(local.classic_user_tags, k) && !can(regex(local.user_tag_pattern, v))])}."
    }
    precondition {
      condition     = !local.sp.enabled || can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", coalesce(local.account_id, "-")))
      error_message = "The serverless usage policy is account-level: set account_id in config/defaults/cost.yaml to the Databricks account ID (a GUID), or set serverless_policy.enabled: false."
    }
    precondition {
      condition     = contains(["ALLOW_ALL", "ALLOW_SLACK", "ALLOW_TEAMS", "DENY_ALL"], coalesce(try(local.settings.collaboration_platforms.allowed, null), "ALLOW_ALL"))
      error_message = "settings collaboration_platforms.allowed must be ALLOW_ALL, ALLOW_SLACK, ALLOW_TEAMS, DENY_ALL or null (leave alone)."
    }
    precondition {
      condition = try(local.workspace.label, null) == null || (
        can(keys(local.workspace.label)) &&
        alltrue([for k in try(keys(local.workspace.label), []) : contains(["text", "color"], k)]) &&
        try(trimspace(local.workspace.label.text), "") != "" &&
        contains(["coral", "lemon", "lime", "turquoise", "indigo", "purple", "pink"], try(local.workspace.label.color, ""))
      )
      error_message = "The workspace file's label needs text (not empty) and color: one of coral, lemon, lime, turquoise, indigo, purple, pink."
    }
    precondition {
      condition = alltrue([
        for k in ["bu", "host"] : try(local.workspace[k], null) != null
      ]) && local.workspace_id != null
      error_message = "The workspace file must set bu and host (an https://adb-<id>.<n>.azuredatabricks.net URL, or set id as well)."
    }
    precondition {
      condition     = alltrue([for p, d in merge(local.personas, { users = local.config.users }) : contains(keys(local.access_tiers), try(d.access, ""))])
      error_message = "access.yaml: every persona's access (and users.access) must be consumer, sql or workspace."
    }
    precondition {
      condition     = alltrue([for k, g in local.config.groups : g == null || can(regex("^[^\\s]", g))]) && length(local.platform_admins) > 0
      error_message = "access.yaml groups: each must be a group name (or null for none), and platform_admins must be set."
    }
    precondition {
      condition     = try(local.settings.compliance_security_profile, null) == null || can(tolist(local.settings.compliance_security_profile))
      error_message = "settings.compliance_security_profile must be null (leave alone) or a list of compliance standards."
    }
  }
}
