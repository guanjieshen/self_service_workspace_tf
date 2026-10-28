variable "settings" {
  description = "Resolved `settings` section of the configuration."
  type        = any
}

variable "genie_code_instructions" {
  description = "Markdown for the workspace's Genie Code instructions. null = leave them alone."
  type        = string
  default     = null
}

variable "genie_code_skills" {
  description = "Genie Code skill files for every user: path under .assistant/skills/ (<skill>/SKILL.md, ...) => base64 content."
  type        = map(string)
  default     = {}
}

variable "default_catalog" {
  description = "The workspace's default catalog (workspace.default_catalog). null = leave it alone."
  type        = string
  default     = null
}

variable "workspace_label" {
  description = "Label shown next to the workspace name in the top bar: { text, color }. null = leave it alone."
  type        = any
  default     = null
}

variable "token_groups" {
  description = "Groups allowed to create personal access tokens."
  type        = list(string)
}

variable "platform_admins" {
  description = "Fallback token users when no persona may create tokens."
  type        = list(string)
}

variable "manage_token_permissions" {
  description = "Manage who may create personal access tokens. false = leave the workspace's token permissions alone."
  type        = bool
  default     = true
}
