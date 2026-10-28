output "team_folder_job_id" {
  value = databricks_job.team_folder.id
}

output "admin_path" {
  value = databricks_directory.admin.path
}
