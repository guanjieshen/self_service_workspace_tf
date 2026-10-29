variable "catalog" {
  description = "The workspace's catalog (catalog.yaml `catalog:`): name, comment, owner, storage_root, workspace_only, predictive_optimization, data_classification."
  type        = any
}

variable "grants" {
  description = "Principal => catalog privileges (persona groups and platform admins)."
  type        = map(list(string))
}
