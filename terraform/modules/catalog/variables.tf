variable "catalog" {
  description = "The workspace's catalog (catalog.yaml `catalog:`): name, comment, owner, storage_root, workspace_only, predictive_optimization, data_classification."
  type        = any
}

variable "usage_policy_id" {
  description = "The serverless usage policy data classification runs on (null: classification is not turned on)."
  type        = string
  default     = null
}

variable "grants" {
  description = "Principal => catalog privileges (persona groups and platform admins)."
  type        = map(list(string))
}
