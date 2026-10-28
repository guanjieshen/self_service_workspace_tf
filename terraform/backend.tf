# Local state by default (scripts/tf.sh stores it in .state/<env>.tfstate).
# For shared state, create config/backend.hcl (see config/backend.hcl.example);
# tf.sh then switches this to the azurerm backend automatically.
terraform {
  backend "local" {}
}
