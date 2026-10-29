# Serverless usage (budget) policies for this workspace, and the tag values cluster policies allow.

locals {
  # ---- Budget policies ----
  bp       = local.config.budget_policies
  lob_tags = { LOB = local.lob }
  # The groups behind each value of used_by: everyone, platform_admins, or a persona.
  policy_audiences = merge(
    { everyone = distinct(flatten(values(local.persona_groups))), platform_admins = local.platform_admins },
    local.persona_groups,
  )
  # used_by as a list (one value or several), per policy.
  policy_used_by = {
    for k, p in try(local.bp.policies, {}) : k => try(tolist(p.used_by), [tostring(p.used_by)], []) if p != null
  }
  budget_policies = {
    for k, p in try(local.bp.policies, {}) : k => {
      name   = replace(replace(tostring(p.name), "{BU}", local.bu_upper), "{bu}", local.bu)
      tags   = merge(local.lob_tags, try(p.tags, {}))
      groups = distinct(flatten([for u in local.policy_used_by[k] : try(local.policy_audiences[u], [])]))
    } if p != null
  }
  budget_policy_managers = distinct(concat(
    [for g in local.platform_admins : "groups/${g}"],
    try(tolist(local.bp.extra_managers), []),
  ))

  # Tag values allowed for each non-LOB required tag on cluster policies.
  shared_tag_values = merge(try(local.config.sql_warehouse.tags, {}), try(local.config.classic_warehouse.tags, {}), try(local.config.shared_cluster.tags, {}))
  allowed_tag_values = {
    for tag in local.config.required_tags : tag => distinct(compact(concat(
      [try(tostring(local.shared_tag_values[tag]), "")],
      [for t in values(local.teams) : try(tostring(t.tags[tag]), "")],
    ))) if tag != "LOB"
  }
}
