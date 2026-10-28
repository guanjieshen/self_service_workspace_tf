variable "root_path" {
  description = "Folder the team folders go in, for example /Workspace (the top of the workspace, which inherits only admins)."
  type        = string
}

variable "job_name" {
  description = "Name of the team folder job."
  type        = string
}

variable "admin_path" {
  description = "Workspace folder for the self-service jobs' notebooks, at the top of the workspace (only admins can see it)."
  type        = string
}

variable "runners" {
  description = "Service principal application IDs that may run the job, besides workspace admins."
  type        = list(string)
  default     = []
}
