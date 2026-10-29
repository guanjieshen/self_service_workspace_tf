# Shared Terraform state in Azure Storage (Entra sign-in only; shared keys are disabled).
# scripts/tf.sh adds key=citizen-dev/<workspace>.tfstate for each workspace.
resource_group_name  = "guanjie-rg"
storage_account_name = "guanjieadls2026"
container_name       = "tfstatetest"
use_azuread_auth     = true
