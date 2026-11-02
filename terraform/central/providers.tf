terraform {
  required_version = ">= 1.9"
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.137"
    }
  }
  # Local state by default; scripts/tf.sh points it at the shared state (citizen-dev/central.tfstate).
  backend "local" {}
}

# The central workspace, signed in to the same way as every workspace: the Azure CLI
# locally, the pipeline's GitHub OIDC sign-in in CI.
provider "databricks" {
  host = local.host # checks.tf explains a missing host
}

# The account: the usage policies' names.
provider "databricks" {
  alias      = "account"
  host       = "https://accounts.azuredatabricks.net"
  account_id = local.account_id
  # The account console cannot tell the tenant from its URL, as a workspace can: CI sets
  # ARM_TENANT_ID; locally, the Azure CLI may be signed in to another tenant by default.
  azure_tenant_id = try(local.setup.tenant_id, null)
}
