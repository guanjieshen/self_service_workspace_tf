# A workspace folder made by scripts/workspaces.py new, and the _example template it copies,
# both plan without errors. Run by scripts/tests/test-scaffold.sh, which creates the
# workspace in a copy of the repository and passes its name as -var workspace=<name>.

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
    condition     = local.bu == "scf" && local.lob == "SCF" && local.workspace_id == "2222222222222222"
    error_message = "workspaces.py new fills bu, lob and host; the workspace ID comes from the host."
  }
  assert {
    condition     = local.default_catalog == "scf_citizen_dev" && local.catalog.name == "scf_citizen_dev"
    error_message = "--catalog sets the default catalog."
  }
  assert {
    condition     = length(regexall("xyz|XYZ", jsonencode([local.persona_groups, local.platform_admins, local.teams, local.group_names]))) == 0
    error_message = "No xyz placeholders are left in the groups, teams or projects."
  }
}

run "example_template" {
  command = plan
  variables {
    workspace = "_example"
  }
}
