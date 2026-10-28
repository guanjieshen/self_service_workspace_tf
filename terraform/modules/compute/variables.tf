variable "names" {
  description = "Name substitutions: {BU}, {bu}."
  type        = map(string)
}

variable "lob" {
  type = string
}

variable "sql_warehouse" {
  description = "Default warehouse settings."
  type        = any
}

variable "classic_warehouse" {
  description = "Optional second, classic (non-serverless) warehouse; created when enabled is true."
  type        = any
}

variable "team_warehouses" {
  description = "Team key => { group, tags, warehouse } for teams with their own warehouse; warehouse is defined in full (name, type, size, scaling, auto-stop)."
  type        = any
}

variable "shared_cluster" {
  type = any
}

variable "cluster_policies" {
  description = "Persona => { template, tags, groups } for personas with a cluster policy."
  type        = any
}

variable "allowed_tag_values" {
  description = "Required tag => allowed values on cluster policies."
  type        = map(list(string))
}

variable "acl" {
  description = "Resolved group => permission maps for sql_warehouse and shared_cluster."
  type        = map(map(string))
}

variable "platform_admins" {
  type = list(string)
}

