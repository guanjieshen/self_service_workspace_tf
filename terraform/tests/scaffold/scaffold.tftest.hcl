# A workspace file copied from _example.yaml and filled in, and the template itself, both plan
# without errors. Run by scripts/tests/test-scaffold.sh, which writes the workspace in a copy
# of the repository and passes its name as -var workspace=<name>.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  use_cli_profiles = false
}

run "scaffolded_workspace" {
  command = plan

  assert {
    condition     = local.bu == "scf" && local.workspace_id == "2222222222222222" && local.account_id == "00000000-0000-0000-0000-000000000000"
    error_message = "bu and host come from the workspace's file, the workspace ID from the host, the account ID from the baseline."
  }
  assert {
    condition     = local.persona_groups == { explorer = ["scf-explorers"] } && local.platform_admins == tolist(["scf_platform_admins"])
    error_message = "Only the personas the file names a group for are granted; the platform admins group comes from the baseline."
  }
  assert {
    condition     = local.catalog.name == "scf_citizen_dev" && local.chargeback_tags.BUSINESS_UNIT == "SCF"
    error_message = "The catalog is named from bu, and so is the BUSINESS_UNIT tag."
  }
}

run "example_template" {
  command = plan
  variables {
    workspace = "_example"
  }
}
