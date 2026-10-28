# Genie Code: the default instructions and skills, plus each workspace's own.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  workspaces_dir   = "tests/fixtures"
  use_cli_profiles = false
}

run "default_only" {
  command = plan
  variables { workspace = "basic" }

  assert {
    condition     = local.manage_genie_instructions && local.manage_genie_skills
    error_message = "Genie Code instructions and skills are managed by default (settings.genie_code)."
  }
  assert {
    condition     = startswith(local.genie_instructions, "# Default instructions") && !strcontains(local.genie_instructions, "# Workspace instructions")
    error_message = "Without its own instructions.md, a workspace gets the default instructions only."
  }
  assert {
    condition     = contains(keys(local.genie_skills), "build-tagged-assets/SKILL.md")
    error_message = "Every workspace gets the default skills."
  }
}

run "default_plus_workspace" {
  command = plan
  variables { workspace = "full" }

  assert {
    condition     = strcontains(local.genie_instructions, "# Default instructions") && strcontains(local.genie_instructions, "# Workspace instructions")
    error_message = "A workspace's instructions.md is appended after the default instructions."
  }
  assert {
    condition     = contains(keys(local.genie_skills), "build-tagged-assets/SKILL.md") && contains(keys(local.genie_skills), "team-howto/SKILL.md")
    error_message = "A workspace's skills are deployed next to the default ones."
  }
}

run "left_alone" {
  command = plan
  variables { workspace = "unmanaged" }

  assert {
    condition     = !local.manage_genie_instructions && !local.manage_genie_skills
    error_message = "settings.genie_code: null leaves Genie Code alone."
  }
  assert {
    condition     = contains(output.released_addresses, "module.workspace_settings.databricks_workspace_file.genie_code_instructions")
    error_message = "Leaving Genie Code alone releases its files instead of deleting them."
  }
}
