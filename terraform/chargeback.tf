# Serverless usage (budget) policies for this workspace, and the tag values cluster policies allow.

locals {
  # ---- Budget policies ----
  bp       = local.config.budget_policies
  lob_tags = { LOB = local.lob }
  # Name templates with {BU} and {bu} filled in.
  policy_names = {
    for k in ["shared_name", "platform_name"] :
    k => replace(replace(local.bp[k], "{BU}", local.bu_upper), "{bu}", local.bu) if contains(keys(local.bp), k)
  }
  budget_policies = merge(
    {
      shared = {
        name   = local.policy_names.shared_name
        tags   = merge(local.lob_tags, local.bp.shared_tags)
        groups = distinct(flatten(values(local.persona_groups))) # every persona
      }
      platform = {
        name   = local.policy_names.platform_name
        tags   = merge(local.lob_tags, local.bp.platform_tags)
        groups = local.platform_admins
      }
    },
  )
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
