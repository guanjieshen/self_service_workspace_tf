# Validation: fails the plan with a plain-language message.

resource "terraform_data" "config_checks" {
  lifecycle {
    precondition {
      condition     = length(local.duplicate_settings) == 0
      error_message = "These settings are defined in more than one file in config/defaults/: ${join(", ", local.duplicate_settings)}."
    }
    precondition {
      condition     = length(local.null_sections) == 0
      error_message = "These sections cannot be null as a whole: ${join(", ", local.null_sections)}. Set the keys inside them to null to leave those alone (only settings, catalog, default_catalog and personal_schemas can be null)."
    }
    precondition {
      condition     = length(local.unknown_overrides) == 0
      error_message = "These keys are not in the baseline (config/defaults/), so they change nothing; check the spelling: ${join(", ", local.unknown_overrides)}."
    }
    precondition {
      condition     = alltrue(flatten([for f, allowed in local.ws_file_keys : [for k in keys(local.ws_parts[f]) : contains(allowed, k)]]))
      error_message = "A workspace file has a setting it does not take. Allowed: ${join("; ", [for f, allowed in local.ws_file_keys : "${f}.yaml: ${join(", ", allowed)}"])}."
    }
    precondition {
      condition = local.catalog == null || (
        can(regex("^[a-z0-9_]+$", try(local.catalog.name, ""))) &&
        alltrue([for k in keys(local.catalog.schemas) : can(regex("^[a-z0-9_]+$", k)) && alltrue([for f in try(keys(local.config.catalog.schemas[k]), []) : contains(["comment", "grants"], f)])])
      )
      error_message = "catalog.yaml catalog: the name and every schema name must be lowercase letters, digits and underscores; a schema may only set comment and grants."
    }
    precondition {
      condition     = local.genie_instructions == null || length(coalesce(local.genie_instructions, "")) <= 19800
      error_message = "Genie Code instructions are ${length(coalesce(local.genie_instructions, ""))} characters (default plus workspace); Genie Code reads at most 20,000. Shorten genie-code/instructions.md."
    }
    precondition {
      condition     = length(local.genie_skill_clashes) == 0
      error_message = "These Genie Code skills exist both in config/defaults/genie-code/skills/ and in this workspace's genie-code/skills/: ${join(", ", local.genie_skill_clashes)}. Give the workspace skill another name."
    }
    precondition {
      condition = alltrue([
        for s in distinct([for f in keys(local.genie_skill_sources) : split("/", f)[0]]) :
        can(regex("^[a-z0-9]+(-[a-z0-9]+)*$", s)) && try(local.genie_skill_meta[s].name, null) == s && try(trimspace(local.genie_skill_meta[s].description), "") != ""
      ])
      error_message = "Each Genie Code skill is a folder named in lowercase letters, digits and hyphens, with a SKILL.md that starts with front matter (between --- lines) giving name: <the folder name> and a description."
    }
    precondition {
      condition     = alltrue([for k, t in local.teams : try(t.warehouse, null) == null])
      error_message = "Team warehouses have moved: define them under team_warehouses in compute.yaml."
    }
    precondition {
      condition     = alltrue([for k in keys(local.team_warehouses) : contains(keys(local.teams), k)])
      error_message = "compute.yaml team_warehouses: every key must be a team in access.yaml (teams: ${join(", ", keys(local.teams))})."
    }
    precondition {
      condition = alltrue([
        for k, w in local.team_warehouses : alltrue([
          for f in ["name", "type", "size", "min_clusters", "max_clusters", "auto_stop_minutes"] : try(w[f], null) != null
        ]) && contains(["serverless", "pro", "classic"], try(w.type, ""))
      ])
      error_message = "Each team warehouse in compute.yaml needs name, type (serverless, pro or classic), size, min_clusters, max_clusters and auto_stop_minutes."
    }
    precondition {
      condition     = contains(["classic", "pro"], try(local.config.classic_warehouse.type, "classic"))
      error_message = "classic_warehouse.type must be classic or pro (the serverless one is sql_warehouse)."
    }
    precondition {
      condition     = can(regex("^(/Workspace)?/[^/]+(/[^/]+)*$", local.config.folders.admin)) && !can(regex("^(/Workspace)?/(Shared|Users|Repos)(/|$)", local.config.folders.admin)) && local.config.folders.admin != "/Workspace"
      error_message = "folders.admin in access.yaml must be a folder at the top of the workspace, for example /Admin/self-service: not under /Shared, /Users or /Repos, which other users can reach. The self-service jobs run with admin rights, so only admins may change their notebooks."
    }
    precondition {
      condition     = alltrue([for r in local.job_runners : can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", r))])
      error_message = "jobs.runners in access.yaml lists service principals by application ID (a GUID), for example a ticketing system's."
    }
    precondition {
      condition     = local.catalog == null || try(local.config.personal_schemas.enabled, false) != true || try(local.catalog.owner, null) == null || local.manage_catalog_grants
      error_message = "The personal schema job needs to keep MANAGE on the catalog once catalog.owner is a group: that comes from the catalog grants this project manages. Keep manage.catalog_grants on, set catalog.owner: null, or turn off personal_schemas."
    }
    precondition {
      condition = alltrue([for k, p in try(local.config.budget_policies.policies, {}) : p == null || (
        can(tostring(p.name)) && length(local.policy_used_by[k]) > 0 &&
        alltrue([for u in local.policy_used_by[k] : contains(keys(local.policy_audiences), u)])
      )])
      error_message = "Each block under budget_policies.policies in cost.yaml needs a name and used_by: everyone, platform_admins, or personas (${join(", ", keys(local.persona_groups))})."
    }
    precondition {
      condition     = try(local.catalog.data_classification, null) != true || local.config.budget_policies.enabled == true
      error_message = "catalog.data_classification needs serverless usage policies (budget_policies.enabled in cost.yaml): data classification runs on serverless and fails without one (\"Usage policy ID must not be empty\"). Turn on budget policies, or set catalog.data_classification: null in this workspace's catalog.yaml."
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
      error_message = "workspace.yaml label needs text (not empty) and color: one of coral, lemon, lime, turquoise, indigo, purple, pink."
    }
    precondition {
      condition = alltrue([
        for k in ["bu", "lob", "account_id", "host"] : try(local.workspace[k], null) != null
      ]) && local.workspace_id != null
      error_message = "workspace.yaml must set bu, lob, account_id and host (an https://adb-<id>.<n>.azuredatabricks.net URL, or set id as well)."
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
          for tag in local.config.required_tags : tag == "LOB" || contains(keys(try(t.tags, {})), tag)
        ]
      ]))
      error_message = "Every team must set these tags: ${join(", ", [for t in local.config.required_tags : t if t != "LOB"])}."
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
