# Validation: fails the plan with a plain-language message (like terraform/checks.tf).
resource "terraform_data" "config_checks" {
  lifecycle {
    precondition {
      condition     = !local.enabled || local.host != null
      error_message = "The cost dashboard needs the central workspace: set host in config/central.yaml, or ai_review_host in config/setup.yaml."
    }
    precondition {
      condition     = !local.enabled || local.catalog != null
      error_message = "config/central.yaml cost_dashboard.catalog: name an existing catalog in the central workspace for the cost view."
    }
    precondition {
      condition     = !local.enabled || !contains(local.managed_catalogs, coalesce(local.catalog, "-"))
      error_message = "config/central.yaml cost_dashboard.catalog: ${coalesce(local.catalog, "-")} is a workspace catalog this repository manages, whose grants are authoritative. Use another catalog."
    }
    precondition {
      condition     = can(tonumber(local.discount_percent)) && tonumber(local.discount_percent) >= 0 && tonumber(local.discount_percent) <= 100
      error_message = "config/central.yaml cost_dashboard.discount_percent: a number from 0 to 100 (your negotiated discount off list price)."
    }
    precondition {
      condition     = !local.enabled || can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", coalesce(local.account_id, "-")))
      error_message = "The cost dashboard names usage policies from the account: set account_id in config/defaults/cost.yaml."
    }
  }
}
