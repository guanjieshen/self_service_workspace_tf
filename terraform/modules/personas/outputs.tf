output "assigned_groups" {
  description = "Group => workspace role."
  value       = { for g, p in databricks_permission_assignment.this : g => p.permissions }
}

output "group_names" {
  description = "Group => its name, once assigned to the workspace. Modules that grant a group a permission take its name from here, so the grant waits for the assignment."
  value       = { for g, a in databricks_permission_assignment.this : g => a.group_name }
}
