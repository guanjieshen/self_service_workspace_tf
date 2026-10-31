variable "workspace" {
  description = "Name of the workspace: its file is config/workspaces/<workspace>.yaml, for example fin-citizen-dev."
  type        = string

  validation {
    condition     = fileexists("${coalesce(var.workspaces_dir, "${path.module}/../config/workspaces")}/${var.workspace}.yaml")
    error_message = "No config/workspaces/<workspace>.yaml found for this workspace."
  }
}

variable "defaults_dir" {
  description = "Folder holding the baseline. Empty = config/defaults/. The tests point it at terraform/tests/defaults/, a copy of the baseline as released, so an organization's own baseline never breaks them."
  type        = string
  default     = ""
}

variable "workspaces_dir" {
  description = "Folder holding the workspace files. Empty = config/workspaces/. The tests (terraform/tests/) point it at their fixtures."
  type        = string
  default     = ""
}

variable "use_cli_profiles" {
  description = "Use the Databricks CLI profiles from the workspace file (auth:). scripts/tf.sh sets this to false in CI."
  type        = bool
  default     = true
}

