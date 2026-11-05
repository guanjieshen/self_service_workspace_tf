# Genie Code: the default instructions and skills, plus each workspace's own.

mock_provider "databricks" {}
mock_provider "databricks" {
  alias = "account"
}

variables {
  defaults_dir     = "tests/defaults"
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
    error_message = "A workspace's genie_code_instructions are appended after the default instructions."
  }
  assert {
    condition     = tolist(keys(local.genie_skills)) == tolist(["build-tagged-assets/SKILL.md", "how-this-workspace-works/SKILL.md", "onboard-me/SKILL.md"])
    error_message = "Every workspace gets the baseline's skills, and only those."
  }
}

run "how_this_workspace_works_describes_this_workspace" {
  command = plan
  variables { workspace = "some-groups" }

  assert {
    condition = alltrue([
      strcontains(local.genie_skill_text["how-this-workspace-works/SKILL.md"], "- **Explorer**: SQL: Databricks One, plus the SQL editor"),
      !strcontains(local.genie_skill_text["how-this-workspace-works/SKILL.md"], "**Builder**"),
      strcontains(local.genie_skill_text["how-this-workspace-works/SKILL.md"], "`TST Classic Interactive`: all-purpose clusters, for notebooks; up to 1 at a time per person, up to 4 workers, stopping after at most 60 idle minutes"),
      length(regexall("\\{(PREFIX|CATALOG|WAREHOUSE|WAREHOUSE_DETAILS|TAGS|WORKSPACE_TAGS|PERSONAS|CLASSIC_POLICIES)\\}", local.genie_skill_text["how-this-workspace-works/SKILL.md"])) == 0,
    ])
    error_message = "The skill lists only the personas this workspace has (here explorer), each classic policy with its limits, and no placeholder unfilled. Got: ${local.genie_skill_text["how-this-workspace-works/SKILL.md"]}"
  }
  assert {
    condition     = !strcontains(local.genie_instructions, "# About our business")
    error_message = "our-business.md holding only comments adds nothing to the instructions."
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
