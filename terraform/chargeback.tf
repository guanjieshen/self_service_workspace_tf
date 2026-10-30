# The chargeback tags (tags: and classic_user_tags in config/defaults/cost.yaml), and the
# workspace's serverless usage policy.

locals {
  # ---- Tags ----
  # The baseline's tags: and the workspace's, key by key (a workspace may add a tag, so this
  # is not the usual merge, which keeps only the baseline's keys), with {BU} / {bu} filled
  # in; a tag set to null in the workspace's file is dropped.
  tag_values = merge(try(local.defaults.tags, {}), try(local.overrides.tags, {}))
  chargeback_tags = {
    for k, v in local.tag_values : k => replace(replace(tostring(v), "{BU}", local.bu_upper), "{bu}", local.bu) if v != null
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
      name   = replace(replace(tostring(local.sp.name), "{BU}", local.bu_upper), "{bu}", local.bu)
      tags   = local.chargeback_tags
      groups = distinct(concat(flatten(values(local.persona_groups)), local.platform_admins))
      # The identity running Terraform uses it too: data classification runs on serverless as
      # whoever turns it on, and fails without a usage policy ("Usage policy ID must not be empty").
      users = compact([try(data.databricks_current_user.pipeline[0].acl_principal_id, "")])
    }
  }
}

# Who runs Terraform (the pipeline's service principal in CI), as a principal for the policy.
data "databricks_current_user" "pipeline" {
  count = local.sp.enabled ? 1 : 0
}
