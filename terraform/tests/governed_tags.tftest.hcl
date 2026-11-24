# Governed tags (terraform/governed_tags.tf): the self-service hub's workspace creates the
# business_unit tag with every workspace's prefix as a value; each workspace tags its catalog.

mock_provider "databricks" {
  override_data {
    target = data.databricks_current_user.me
    values = { user_name = "33333333-3333-3333-3333-333333333333" }
  }
}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
  workspaces_dir   = "tests/fixtures"
  use_cli_profiles = false
  workspace        = "full"
}

run "the_hub_creates_the_tag_and_tags_its_catalog" {
  command = plan
  variables { self_service_dir = "tests/self-service-hub-is-this-workspace" }

  assert {
    condition     = length(databricks_tag_policy.business_unit) == 1 && databricks_tag_policy.business_unit[0].tag_key == "business_unit"
    error_message = "The hub's workspace owns the governed tag."
  }
  assert {
    condition     = toset([for v in databricks_tag_policy.business_unit[0].values : v.name]) == toset(["tst"])
    error_message = "Its allowed values are every workspace file's prefix, lower case."
  }
  assert {
    condition     = length(databricks_entity_tag_assignment.catalog_business_unit) == 1 && databricks_entity_tag_assignment.catalog_business_unit[0].entity_type == "catalogs" && databricks_entity_tag_assignment.catalog_business_unit[0].tag_value == "tst"
    error_message = "The hub tags its own catalog with its prefix, in the same apply."
  }
  assert {
    condition     = local.gt_managers == local.platform_admins && contains(local.gt_managers, "tst-admins")
    error_message = "With managers: null, the hub's platform admins manage the tag."
  }
  assert {
    condition     = alltrue([for g in ["tst_users", "tst-explorers", "tst-builders", "tst-publishers", "tst-admins"] : contains(local.gt_assigners, g)])
    error_message = "Every workspace's persona groups and platform admins may assign the tag. Got: ${join(", ", local.gt_assigners)}"
  }
  assert {
    condition     = local.gt_pipeline == "servicePrincipals/33333333-3333-3333-3333-333333333333"
    error_message = "The pipeline may assign it too: it tags the catalogs."
  }
}

run "another_workspace_waits_until_its_value_is_allowed" {
  command = plan
  variables { self_service_dir = "tests/self-service" }

  assert {
    condition     = length(databricks_tag_policy.business_unit) == 0 && length(databricks_access_control_rule_set.business_unit) == 0
    error_message = "Only the hub's workspace creates the governed tag."
  }
  assert {
    condition     = length(databricks_entity_tag_assignment.catalog_business_unit) == 0
    error_message = "Before the hub allows its value, the catalog is left untagged (the plan does not fail)."
  }
}

# Tagging once the hub allows the value reads data.databricks_tag_policies, whose nested list
# Terraform's mocks cannot fill in: that path is checked against a real workspace.
