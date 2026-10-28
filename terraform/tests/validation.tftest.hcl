# Validation: each fixture under fixtures/invalid/ breaks one rule, and the plan must fail
# with a precondition in checks.tf (terraform_data.config_checks). Add a fixture and a run
# here for every new check.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  workspaces_dir   = "tests/fixtures/invalid"
  use_cli_profiles = false
}

# A workspace file has a setting it does not take
run "unknown_key" {
  command = plan
  variables { workspace = "unknown-key" }
  expect_failures = [terraform_data.config_checks]
}

# catalog.yaml catalog: needs a name of lowercase letters
run "bad_catalog_name" {
  command = plan
  variables { workspace = "bad-catalog-name" }
  expect_failures = [terraform_data.config_checks]
}

# catalog.yaml catalog: may only set
run "catalog_unknown_field" {
  command = plan
  variables { workspace = "catalog-unknown-field" }
  expect_failures = [terraform_data.config_checks]
}

# exist both in config/defaults and in this workspace
run "skill_clash" {
  command = plan
  variables { workspace = "skill-clash" }
  expect_failures = [terraform_data.config_checks]
}

# SKILL.md name must equal the folder name
run "skill_name_mismatch" {
  command = plan
  variables { workspace = "skill-name-mismatch" }
  expect_failures = [terraform_data.config_checks]
}

# SKILL.md needs a description
run "skill_no_description" {
  command = plan
  variables { workspace = "skill-no-description" }
  expect_failures = [terraform_data.config_checks]
}

# skill folders are lowercase letters, digits and hyphens
run "skill_bad_folder" {
  command = plan
  variables { workspace = "skill-bad-folder" }
  expect_failures = [terraform_data.config_checks]
}

# team warehouses have moved to compute.yaml
run "team_warehouse_in_team" {
  command = plan
  variables { workspace = "team-warehouse-in-team" }
  expect_failures = [terraform_data.config_checks]
}

# team_warehouses keys must be teams
run "team_warehouse_no_team" {
  command = plan
  variables { workspace = "team-warehouse-no-team" }
  expect_failures = [terraform_data.config_checks]
}

# team warehouses are defined in full
run "team_warehouse_fields" {
  command = plan
  variables { workspace = "team-warehouse-fields" }
  expect_failures = [terraform_data.config_checks]
}

# compute.yaml sql_warehouse may only set keys the baseline has
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

# workspace.yaml must give the host
run "workspace_missing_host" {
  command = plan
  variables { workspace = "workspace-missing-host" }
  expect_failures = [terraform_data.config_checks]
}

# access.yaml personas may only use defined personas
run "unknown_persona" {
  command = plan
  variables { workspace = "unknown-persona" }
  expect_failures = [terraform_data.config_checks]
}

# every team sets the required tags
run "team_missing_tag" {
  command = plan
  variables { workspace = "team-missing-tag" }
  expect_failures = [terraform_data.config_checks]
}

# team keys are lowercase letters, digits and dashes
run "team_bad_key" {
  command = plan
  variables { workspace = "team-bad-key" }
  expect_failures = [terraform_data.config_checks]
}

# every team needs a group
run "team_no_group" {
  command = plan
  variables { workspace = "team-no-group" }
  expect_failures = [terraform_data.config_checks]
}

# access.yaml groups must name the platform admins group
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

# a team without tags fails the required-tags check, not with an error
run "team_no_tags" {
  command = plan
  variables { workspace = "team-no-tags" }
  expect_failures = [terraform_data.config_checks]
}

# workspace.yaml label needs text and one of the allowed colors
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

# Data classification needs serverless usage policies
run "classification_without_usage_policies" {
  command = plan
  variables { workspace = "classification-without-usage-policies" }
  expect_failures = [terraform_data.config_checks]
}

# The personal schema job keeps MANAGE on a group-owned catalog only through the managed grants
run "personal_schemas_without_catalog_grants" {
  command = plan
  variables { workspace = "personal-schemas-without-catalog-grants" }
  expect_failures = [terraform_data.config_checks]
}

# Only some sections can be null as a whole
run "null_section" {
  command = plan
  variables { workspace = "null-section" }
  expect_failures = [terraform_data.config_checks]
}

# The self-service notebooks must not live where users can change them
run "admin_folder_under_shared" {
  command = plan
  variables { workspace = "admin-folder-under-shared" }
  expect_failures = [terraform_data.config_checks]
}

# Job runners are service principals, given by application ID
run "runner_not_an_id" {
  command = plan
  variables { workspace = "runner-not-an-id" }
  expect_failures = [terraform_data.config_checks]
}

