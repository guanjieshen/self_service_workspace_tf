# The workspace's Unity Catalog catalog and who may use it. Schemas in it are not
# Terraform's: people create them through the self-service app.
# Deleting a catalog deletes its tables, views and volumes; force_destroy stays off so
# Terraform cannot delete one that still holds data.
resource "databricks_catalog" "this" {
  name         = var.catalog.name
  comment      = try(var.catalog.comment, null)
  owner        = try(var.catalog.owner, null) # null = leave the owner alone
  storage_root = try(var.catalog.storage_root, null)
  # ISOLATED: only this workspace can use the catalog.
  isolation_mode = try(var.catalog.workspace_only, true) ? "ISOLATED" : "OPEN"
  # Schemas inherit it. null = leave alone.
  enable_predictive_optimization = try(var.catalog.predictive_optimization, null) == null ? null : (var.catalog.predictive_optimization ? "ENABLE" : "DISABLE")
}

# Data classification for the whole catalog (every schema, new ones too).
resource "databricks_data_classification_catalog_config" "this" {
  count  = try(var.catalog.data_classification, null) == true ? 1 : 0
  parent = "catalogs/${databricks_catalog.this.name}"
}

# Who may use the catalog. Schemas, tables and views inherit these privileges.
# Authoritative: the list replaces any other grants on the catalog.
resource "databricks_grants" "catalog" {
  count   = length(var.grants) > 0 ? 1 : 0
  catalog = databricks_catalog.this.name

  dynamic "grant" {
    for_each = var.grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}
