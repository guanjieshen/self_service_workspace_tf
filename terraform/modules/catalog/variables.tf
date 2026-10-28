variable "catalog" {
  description = "The workspace's catalog (catalog.yaml `catalog:`): name, comment, owner, storage_root, workspace_only, schemas."
  type        = any
}

variable "grants" {
  description = "Principal => catalog privileges (persona groups and platform admins). Empty = leave catalog grants alone."
  type        = map(list(string))
}

variable "personal_schemas_enabled" {
  description = "Deploy the personal schema job. A plain boolean so the plan knows the count before apply."
  type        = bool
  default     = false
}

variable "personal_schemas" {
  description = "catalog.yaml personal_schemas (prefix, privileges) plus job_name. Used when personal_schemas_enabled."
  type        = any
  default     = null
}

variable "admin_path" {
  description = "Workspace folder for the personal schema notebook (only admins can see it)."
  type        = string
  default     = null
}

variable "runners" {
  description = "Service principal application IDs that may run the personal schema job, besides workspace admins."
  type        = list(string)
  default     = []
}
