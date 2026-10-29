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
      condition     = alltrue([for k, t in local.teams : try(t.warehouse, null) == null])
      error_message = "Team warehouses go under team_warehouses in the workspace file, not inside a team."
    }
    precondition {
      condition     = alltrue([for k in keys(local.team_warehouses) : contains(keys(local.teams), k)])
      error_message = "team_warehouses: every key must be one of the workspace's teams (teams: ${join(", ", keys(local.teams))})."
    }
    precondition {
      condition = alltrue([
        for k, w in local.team_warehouses : alltrue([
          for f in ["name", "type", "size", "min_clusters", "max_clusters", "auto_stop_minutes"] : try(w[f], null) != null
        ]) && contains(["serverless", "pro", "classic"], try(w.type, ""))
      ])
      error_message = "Each team warehouse (team_warehouses in the workspace's file) needs name, type (serverless, pro or classic), size, min_clusters, max_clusters and auto_stop_minutes."
    }
    precondition {
      condition     = contains(["classic", "pro"], try(local.config.classic_warehouse.type, "classic"))
      error_message = "classic_warehouse.type must be classic or pro (the serverless one is sql_warehouse)."
    }
    precondition {
      condition = alltrue([for k, p in try(local.config.budget_policies.policies, {}) : p == null || (
        can(tostring(p.name)) && length(local.policy_used_by[k]) > 0 &&
        alltrue([for u in local.policy_used_by[k] : contains(keys(local.policy_audiences), u)])
      )])
      error_message = "Each block under budget_policies.policies (config/defaults/cost.yaml or the workspace's file) needs a name and used_by: everyone, platform_admins, or personas (${join(", ", keys(local.persona_groups))})."
    }
    precondition {
      condition     = !local.config.budget_policies.enabled || can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", coalesce(local.account_id, "-")))
      error_message = "Budget policies are account-level: set account_id in config/defaults/cost.yaml to the Databricks account ID (a GUID), or set budget_policies.enabled: false."
    }
    precondition {
      condition     = try(local.catalog.data_classification, null) != true || local.config.budget_policies.enabled == true
      error_message = "catalog.data_classification needs serverless usage policies (budget_policies.enabled in config/defaults/cost.yaml): data classification runs on serverless and fails without one (\"Usage policy ID must not be empty\"). Turn on budget policies, or set catalog.data_classification: null in this workspace's catalog.yaml."
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
      condition = alltrue(flatten([
        for k, t in local.teams : [
          for tag in local.config.required_tags : contains(keys(local.workspace_tags), tag) || contains(keys(try(t.tags, {})), tag)
        ]
      ]))
      error_message = "Every team must set these required tags (the ones the workspace's tags: does not set): ${join(", ", [for t in local.config.required_tags : t if !contains(keys(local.workspace_tags), t)])}."
    }
    precondition {
      condition     = alltrue([for k in keys(local.teams) : can(regex("^[a-z0-9][a-z0-9-]*$", k))])
      error_message = "Team keys must be lowercase letters, digits and dashes (they are used in folder and policy names)."
    }
    precondition {
      condition     = alltrue([for k, t in local.teams : try(t.group, null) != null])
      error_message = "Every team needs a group."
    }
    precondition {
      condition     = try(local.settings.compliance_security_profile, null) == null || can(tolist(local.settings.compliance_security_profile))
      error_message = "settings.compliance_security_profile must be null (leave alone) or a list of compliance standards."
    }
  }
}
