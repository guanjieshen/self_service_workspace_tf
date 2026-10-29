# Sign-in comes from the CLI profiles in the workspace file (auth:, local runs) or from
# DATABRICKS_* environment variables set by .github/actions/setup (CI).
locals {
  account_host = "https://accounts.azuredatabricks.net" # Azure Databricks account console
}

# Workspace-level provider: everything except budget policies.
provider "databricks" {
  host    = try(local.workspace.host, null) # checks.tf explains a missing host
  profile = var.use_cli_profiles ? local.auth.workspace_profile : null
}

# Account-level provider: budget policies and their access rules only.
provider "databricks" {
  alias      = "account"
  host       = local.account_host
  account_id = local.account_id
  profile    = var.use_cli_profiles ? local.auth.account_profile : null
}
