variable "config_dir" {
  description = "Folder holding central.yaml and setup.yaml. Empty = config/. The tests point it at their fixtures."
  type        = string
  default     = ""
}

variable "workspaces_dir" {
  description = "Folder holding the workspace files. Empty = config/workspaces/."
  type        = string
  default     = ""
}

variable "defaults_dir" {
  description = "Folder holding the baseline. Empty = config/defaults/."
  type        = string
  default     = ""
}

variable "policy_names" {
  description = "Usage policy ID => name, instead of reading them from the account: for the tests, or an account whose policy list the pipeline cannot read. null = read them."
  type        = map(string)
  default     = null
}
