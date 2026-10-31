# The chargeback tags (tags: and classic_user_tags in config/defaults/cost.yaml), and the
# workspace's serverless usage policy.

locals {
  # ---- Tags ----
  # The baseline's tags: and the workspace's, key by key (a workspace may add a tag, so this
  # is not the usual merge, which keeps only the baseline's keys), with {PREFIX} / {prefix} filled
  # in; a tag set to null in the workspace's file is dropped.
  tag_values = merge(try(local.defaults.tags, {}), try(local.overrides.tags, {}))
  chargeback_tags = {
    for k, v in local.tag_values : k => replace(replace(tostring(v), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix) if v != null
  }
  classic_user_tags = [for t in try(tolist(local.config.classic_user_tags), []) : tostring(t)]
  # What a user may type in a classic_user_tags tag: one spelling per value.
  user_tag_pattern = "^[A-Z0-9_-]+$"
  # Every tag key, for the Genie Code text ({TAGS}).
  all_tag_keys = distinct(concat(keys(local.chargeback_tags), local.classic_user_tags))

  # ---- Serverless usage policy ----
  sp = local.config.serverless_policy
  serverless_policies = {
    self_service = {
      name   = replace(replace(tostring(local.sp.name), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)
      tags   = local.chargeback_tags
      groups = distinct(concat(flatten(values(local.persona_groups)), local.platform_admins))
    }
  }
}
