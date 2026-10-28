# The admin folder for the self-service jobs' notebooks, and the team folder job.
# The admin folder sits at the top of the workspace, which grants only workspace admins:
# the jobs run with admin rights, so only admins may change their notebooks.
# Terraform deploys the job, not the folders: an admin (or a runner, such as a ticketing system) runs it
# with a folder name, the requester and, optionally, a group of theirs that owns it too.
resource "databricks_directory" "admin" {
  path = var.admin_path
}

resource "databricks_notebook" "team_folder" {
  path     = "${databricks_directory.admin.path}/team_folder"
  language = "PYTHON"
  # The settings from access.yaml are written into the notebook, where a run cannot
  # change them (a run can pass any parameter, so they cannot be task parameters).
  content_base64 = base64encode(templatefile("${path.module}/team_folder.py", {
    root = var.root_path
  }))
}

resource "databricks_job" "team_folder" {
  name                = var.job_name
  max_concurrent_runs = 20 # requests run side by side, each on its own serverless compute

  queue {
    enabled = true # more requests than that wait their turn
  }

  # How automation (a ticketing system, a self-service app) finds the job in each workspace.
  tags = { cd_self_service = "team_folder", cd_root = var.root_path }

  # What a request sets.
  dynamic "parameter" {
    for_each = toset(["folder", "requested_by", "owner_group", "reason", "request_id"])
    content {
      name    = parameter.value
      default = ""
    }
  }

  task {
    task_key        = "create"
    max_retries     = 0
    timeout_seconds = 600

    notebook_task {
      source        = "WORKSPACE"
      notebook_path = databricks_notebook.team_folder.path
    }
  }
}

# Only workspace admins (and the owner) can see and run the job, plus these service
# principals (jobs.runners in access.yaml), for example a ticketing system's.
resource "databricks_permissions" "team_folder_job" {
  count  = length(var.runners) > 0 ? 1 : 0
  job_id = databricks_job.team_folder.id

  dynamic "access_control" {
    for_each = var.runners
    content {
      service_principal_name = access_control.value
      permission_level       = "CAN_MANAGE_RUN"
    }
  }
}
