variable "names" {
  description = "Name substitutions: {BU}, {bu}."
  type        = map(string)
}

variable "tags" {
  description = "The chargeback tags (key => value), on the warehouse and fixed on every cluster the policy creates."
  type        = map(string)
}

variable "classic_user_tags" {
  description = "Tags the user fills in on a classic cluster, required and matching user_tag_pattern."
  type        = list(string)
}

variable "user_tag_pattern" {
  description = "Regular expression a classic_user_tags value must match."
  type        = string
}

variable "sql_warehouse" {
  description = "Default warehouse settings."
  type        = any
}

variable "cluster_policy" {
  description = "The classic cluster policies' shared rules, and interactive, jobs and pipelines (config/defaults/compute.yaml cluster_policy)."
  type        = any
}

variable "warehouse_acl" {
  description = "Resolved group => permission on the default warehouse."
  type        = map(string)
}

variable "starter_warehouse" {
  description = "IDs of the Serverless Starter Warehouse (none, or one): only the platform admins may use it."
  type        = list(string)
  default     = []
}

variable "platform_admins" {
  type = list(string)
}
