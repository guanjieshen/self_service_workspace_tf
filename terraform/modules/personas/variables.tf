variable "personas" {
  description = "Persona definitions from config/defaults/access.yaml (after overrides)."
  type        = any
}

variable "persona_groups" {
  description = "Persona name => groups holding that persona."
  type        = map(list(string))
}

variable "platform_admins" {
  description = "Groups that administer the workspace."
  type        = list(string)
}

variable "platform_admin_role" {
  description = "Workspace role for platform admin groups: ADMIN or USER."
  type        = string
}

variable "extra_groups" {
  description = "Team and project groups that must be assigned to the workspace (no entitlements managed)."
  type        = list(string)
}

variable "users_group_entitlements" {
  description = "Entitlements for the built-in users group, or null to leave it unmanaged."
  type        = any
}

variable "manage_assignment" {
  description = "Assign groups to the workspace. false = they are already in the workspace (assigned elsewhere, or workspace-local groups)."
  type        = bool
  default     = true
}
