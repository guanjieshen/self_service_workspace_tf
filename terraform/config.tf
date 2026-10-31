# Loads the YAML configuration and merges the baseline with this workspace's choices.
# The configuration logic is split over these files; nobody needs to edit them to run a workspace:
#   config.tf      loading and merging
#   overrides.tf   what a workspace file may set, and what "leave alone" releases
#   access.tf      persona groups and the permission each group gets
#   chargeback.tf  the chargeback tags and the serverless usage policy
#   checks.tf      validation with plain-language error messages

locals {
  project_root = abspath("${path.module}/..")

  # ---- Baseline: every YAML file under config/defaults/ (except genie-code/) ----
  # A section may be split across files;
  # each setting must appear in only one file.
  defaults_dir      = var.defaults_dir == "" ? "${local.project_root}/config/defaults" : var.defaults_dir
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

  # ---- This workspace: config/workspaces/<workspace>.yaml ----
  # One file: who the workspace is (workspace_keys), and any baseline key it changes, at the
  # top level with the same name and shape. A file with only comments counts as empty.
  ws_file = "${coalesce(var.workspaces_dir, "${local.project_root}/config/workspaces")}/${var.workspace}.yaml"
  ws_all  = try({ for k, v in yamldecode(file(local.ws_file)) : k => v }, {})
  # Keys only a workspace has, besides the baseline's own sections.
  workspace_keys = ["prefix", "host", "id", "label", "auth", "genie_code_instructions"]
  workspace      = { for k in setsubtract(local.workspace_keys, ["genie_code_instructions"]) : k => local.ws_all[k] if contains(keys(local.ws_all), k) }
  # Keys that are neither a baseline section nor a workspace key (usually a typo).
  unknown_keys = [for k in keys(local.ws_all) : k if !contains(concat(local.defaults_sections, local.workspace_keys), k)]

  # Merge rule, per top-level section of config/defaults/ (overrides: the same key in the
  # workspace's file):
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

  # The workspace ID: id in the workspace file, or the number in an Azure workspace URL (adb-<id>.<n>).
  workspace_id = try(tostring(local.workspace.id), regex("adb-([0-9]+)\\.", local.workspace.host)[0], null)

  # The Databricks account: the baseline's (config/defaults/cost.yaml), or the workspace file's.
  account_id   = try(tostring(local.config.account_id), null)
  prefix       = lower(try(local.workspace.prefix, ""))
  prefix_upper = upper(try(local.workspace.prefix, ""))
  auth = {
    workspace_profile = try(local.workspace.auth.workspace_profile, null)
    account_profile   = try(local.workspace.auth.account_profile, null)
  }

  # settings: null in a workspace file leaves every admin setting alone.
  settings = [local.config.settings, { for k in keys(local.defaults.settings) : k => null }][local.config.settings == null ? 1 : 0]
  personas = local.config.personas
}
