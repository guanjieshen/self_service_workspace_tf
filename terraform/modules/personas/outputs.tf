output "assigned_groups" {
  description = "Group => workspace role."
  value       = { for g, p in databricks_permission_assignment.this : g => p.permissions }
}

output "group_names" {
  description = "Group => its name, once assigned to the workspace. Modules that grant a group a permission take its name from here, so the grant waits for the assignment."
  value       = { for g, a in databricks_permission_assignment.this : g => a.group_name }
}

output "sharing_entitlements" {
  description = "Sharing group => its entitlements (every one off)."
  value = { for g, e in databricks_entitlements.sharing : g => {
    workspace_access = e.workspace_access, databricks_sql_access = e.databricks_sql_access, allow_cluster_create = e.allow_cluster_create
  } }
}
