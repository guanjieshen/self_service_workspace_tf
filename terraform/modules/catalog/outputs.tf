output "name" {
  value = databricks_catalog.this.name
}

output "schemas" {
  value = [for s in databricks_schema.this : s.id]
}

output "personal_schema_job_id" {
  value = try(databricks_job.personal_schemas[0].id, null)
}
