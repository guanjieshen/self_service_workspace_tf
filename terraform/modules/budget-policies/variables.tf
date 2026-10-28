variable "account_id" {
  type = string
}

variable "workspace_id" {
  description = "Workspace the policies are bound to."
  type        = number
}

variable "policies" {
  description = "Key => { name, tags, groups }."
  type        = any
}

variable "managers" {
  description = "Principals (groups/<name>, users/<email>, servicePrincipals/<app-id>) that manage every policy."
  type        = list(string)
}
