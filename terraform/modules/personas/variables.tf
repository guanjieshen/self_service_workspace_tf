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
  description = "Other groups to assign to the workspace with no entitlements managed here (the users group)."
  type        = list(string)
}

variable "users_group_entitlements" {
  description = "Entitlements for the built-in users group, or null to leave it unmanaged."
  type        = any
}
