# Loads the YAML configuration and merges the baseline with this workspace's choices.
# The configuration logic is split over these files; nobody needs to edit them to run a workspace:
#   config.tf      loading and merging
#   overrides.tf   what a workspace file may set, and what "leave alone" releases
#   access.tf      persona groups and the permission each group gets
#   chargeback.tf  serverless usage (budget) policies and allowed tag values
#   checks.tf      validation with plain-language error messages

locals {
  project_root = abspath("${path.module}/..")

  # ---- Baseline: every YAML file under config/defaults/ (except genie-code/) ----
  # A section may be split across files;
  # each setting must appear in only one file.
  defaults_dir      = "${local.project_root}/config/defaults"
  defaults_files    = sort([for f in fileset(local.defaults_dir, "**/*.yaml") : f if !strcontains(f, "genie-code/")])
  defaults_parts    = [for f in local.defaults_files : try({ for k, v in yamldecode(file("${local.defaults_dir}/${f}")) : k => v }, {})]
  defaults_sections = distinct(flatten([for part in local.defaults_parts : keys(part)]))
  defaults_by_section = {
    for s in local.defaults_sections : s => [for part in local.defaults_parts : part[s] if contains(keys(part), s)]
  }
  defaults = {
    # One file: its value as is. Several: merged (merge() would turn a single null into {}).
    for s, values in local.defaults_by_section : s => [values[0], try(merge(values...), values[0])][length(values) == 1 ? 0 : 1]
  }
  # Setting names per section across all files ("*" stands for a whole list section).
  defaults_setting_names = {
    for s, values in local.defaults_by_section : s => flatten([for v in values : try(keys(v), ["*"])])
  }
  duplicate_settings = flatten([
    for s, names in local.defaults_setting_names : [
      for n in distinct(names) : "${s}.${n}" if length([for x in names : x if x == n]) > 1
    ]
  ])

  # ---- This workspace: config/workspaces/<workspace>/*.yaml, one file per part ----
  # A missing file, or one with only comments, counts as empty (baseline values).
  ws_dir = "${coalesce(var.workspaces_dir, "${local.project_root}/config/workspaces")}/${var.workspace}"
  # The keys each workspace file may set: the sections of the baseline file of the same
  # name (overrides), plus the workspace-only keys in overrides.tf.
  default_sections = { for i, f in local.defaults_files : trimsuffix(f, ".yaml") => keys(local.defaults_parts[i]) }
  ws_file_keys = {
    workspace = ["bu", "lob", "account_id", "host", "id", "ci", "label", "auth"]
    access    = concat(try(local.default_sections.access, []), local.workspace_only_keys.access)
    compute   = concat(try(local.default_sections.compute, []), local.workspace_only_keys.compute)
    cost      = try(local.default_sections.cost, [])
    catalog   = try(local.default_sections.catalog, [])
    settings  = try(local.default_sections.settings, [])
  }
  ws_parts = {
    for f in keys(local.ws_file_keys) : f => try({ for k, v in yamldecode(file("${local.ws_dir}/${f}.yaml")) : k => v }, {})
  }
  workspace       = local.ws_parts.workspace
  access_file     = local.ws_parts.access
  team_warehouses = try({ for k, v in local.ws_parts.compute.team_warehouses : k => v }, {})

  # Merge rule, per top-level section of config/defaults/ (overrides come from the
  # workspace's file of the same name, overrides.tf):
  #   - a key missing from the workspace file keeps the default;
  #   - a key set to null becomes null (Terraform leaves the setting alone);
  #   - a map value is merged key by key; any other value is replaced.
  # A section that is not a map (a list) is replaced as a whole; a section set to null
  # (for example catalog: null) becomes null.
  # The [..][index] form picks one value without Terraform unifying their types.
  config = {
    for section, base in local.defaults : section => [
      [base, try(local.overrides[section], null)][contains(keys(local.overrides), section) ? 1 : 0],
      try(
        {
          for key in keys(base) : key => [
            base[key],
            null,
            try(merge(base[key], local.overrides[section][key]), local.overrides[section][key], null),
            ][
            !contains(keys(try(local.overrides[section], {})), key) ? 0 :
            local.overrides[section][key] == null ? 1 : 2
          ]
        },
        base,
      ),
      null,
      ][
      # A whole section set to null in the workspace file: null (leave it alone).
      contains(keys(local.overrides), section) && try(local.overrides[section] == null, false) ? 2 :
      can(keys(base)) ? 1 : 0
    ]
  }

  # The workspace ID: id in workspace.yaml, or the number in an Azure workspace URL (adb-<id>.<n>).
  workspace_id = try(tostring(local.workspace.id), regex("adb-([0-9]+)\\.", local.workspace.host)[0], null)

  bu       = lower(local.workspace.bu)
  bu_upper = upper(local.workspace.bu)
  lob      = tostring(local.workspace.lob)
  auth = {
    workspace_profile = try(local.workspace.auth.workspace_profile, null)
    account_profile   = try(local.workspace.auth.account_profile, null)
  }

  # settings: null in a workspace file leaves every admin setting alone.
  settings = [local.config.settings, { for k in keys(local.defaults.settings) : k => null }][local.config.settings == null ? 1 : 0]
  personas = local.config.personas
}
