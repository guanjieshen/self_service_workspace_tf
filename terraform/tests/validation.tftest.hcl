# Validation: each fixture under fixtures/invalid/ breaks one rule, and the plan must fail
# with a precondition in checks.tf (terraform_data.config_checks). Add a fixture and a run
# here for every new check.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures/invalid"
  use_cli_profiles = false
}

# A workspace file has a setting it does not take
run "unknown_key" {
  command = plan
  variables { workspace = "unknown-key" }
  expect_failures = [terraform_data.config_checks]
}

# catalog: needs a name of lowercase letters
run "bad_catalog_name" {
  command = plan
  variables { workspace = "bad-catalog-name" }
  expect_failures = [terraform_data.config_checks]
}

# catalog: may only set
run "catalog_unknown_field" {
  command = plan
  variables { workspace = "catalog-unknown-field" }
  expect_failures = [terraform_data.config_checks]
}

# sql_warehouse may only set keys the baseline has
run "warehouse_unknown_key" {
  command = plan
  variables { workspace = "warehouse-unknown-key" }
  expect_failures = [terraform_data.config_checks]
}

# A workspace can only override personas the baseline defines
run "override_unknown_persona" {
  command = plan
  variables { workspace = "override-unknown-persona" }
  expect_failures = [terraform_data.config_checks]
}

# a workspace file must give the host
run "workspace_missing_host" {
  command = plan
  variables { workspace = "workspace-missing-host" }
  expect_failures = [terraform_data.config_checks]
}

# personas may only use defined personas
run "unknown_persona" {
  command = plan
  variables { workspace = "unknown-persona" }
  expect_failures = [terraform_data.config_checks]
}

# groups must name the platform admins group
run "no_platform_admins" {
  command = plan
  variables { workspace = "no-platform-admins" }
  expect_failures = [terraform_data.config_checks]
}

# Genie Code instructions are limited to 20,000 characters
run "instructions_too_long" {
  command = plan
  variables { workspace = "instructions-too-long" }
  expect_failures = [terraform_data.config_checks]
}

# a workspace file's label needs text and one of the allowed colors
run "bad_label" {
  command = plan
  variables { workspace = "bad-label" }
  expect_failures = [terraform_data.config_checks]
}

# A misspelt setting under settings: is not in the baseline
run "unknown_override" {
  command = plan
  variables { workspace = "unknown-override" }
  expect_failures = [terraform_data.config_checks]
}

# Data classification needs the serverless usage policy
run "classification_without_usage_policies" {
  command = plan
  variables { workspace = "classification-without-usage-policies" }
  expect_failures = [terraform_data.config_checks]
}

# Only some sections can be null as a whole
run "null_section" {
  command = plan
  variables { workspace = "null-section" }
  expect_failures = [terraform_data.config_checks]
}


# A key that was removed (team config now comes from the self-service app) is an unknown key
run "removed_teams_key" {
  command = plan
  variables { workspace = "removed-teams-key" }
  expect_failures = [terraform_data.config_checks]
}

# A tag users fill in on classic clusters starts from a value they could not type (lower case)
run "user_tag_bad_default" {
  command = plan
  variables { workspace = "user-tag-bad-default" }
  expect_failures = [terraform_data.config_checks]
}

# A tag key with a space
run "bad_tag_key" {
  command = plan
  variables { workspace = "bad-tag-key" }
  expect_failures = [terraform_data.config_checks]
}

# Data classification cannot be turned on by Terraform yet (the provider cannot send its usage policy)
run "classification_on" {
  command = plan
  variables { workspace = "classification-on" }
  expect_failures = [terraform_data.config_checks]
}
