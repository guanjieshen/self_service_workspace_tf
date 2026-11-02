# What the central workspace gets, from config/central.yaml, and who sees what, from every
# workspace's file (the same files the per-workspace root module reads).

locals {
  config_dir     = coalesce(var.config_dir, "${path.module}/../../config")
  workspaces_dir = coalesce(var.workspaces_dir, "${local.config_dir}/workspaces")
  defaults_dir   = coalesce(var.defaults_dir, "${local.config_dir}/defaults")

  central = try(yamldecode(file("${local.config_dir}/central.yaml")), {})
  setup   = try(yamldecode(file("${local.config_dir}/setup.yaml")), {})
  # try(), not a conditional: a conditional would turn every value in the block into a string.
  cd      = try(local.central.cost_dashboard, {})
  enabled = tostring(try(local.cd.enabled, false)) == "true"

  host       = try(coalesce(try(local.central.host, null), try(local.setup.ai_review_host, null)), null)
  account_id = try(yamldecode(file("${local.defaults_dir}/cost.yaml")).account_id, null)

  catalog          = try(local.cd.catalog, null)
  schema           = coalesce(try(local.cd.schema, null), "cost")
  discount_percent = coalesce(try(local.cd.discount_percent, null), 0)
  dashboard_name   = coalesce(try(local.cd.name, null), "Citizen development costs")
  folder           = coalesce(try(local.cd.folder, null), "/Workspace/Shared/Citizen development")
  warehouse_size   = coalesce(try(local.cd.warehouse_size, null), "2X-Small")
  given_warehouse  = try(local.cd.warehouse_id, null)

  # ---- Every managed workspace: its ID, prefix and the groups that may see its costs ----
  # The groups are a workspace's persona groups and its platform admins, named exactly as
  # terraform/access.tf names them ({prefix} / {PREFIX} filled in).
  default_groups  = try(yamldecode(file("${local.defaults_dir}/access.yaml")).groups, {})
  workspace_files = sort([for f in fileset(local.workspaces_dir, "*.yaml") : f if !startswith(f, "_")])
  workspaces = {
    for f in local.workspace_files : trimsuffix(f, ".yaml") => yamldecode(file("${local.workspaces_dir}/${f}"))
  }
  members = {
    for name, w in local.workspaces : name => {
      prefix = lower(w.prefix)
      host   = trimsuffix(w.host, "/")
      id     = tostring(try(w.id, regex("adb-([0-9]+)\\.", w.host)[0]))
      groups = sort(distinct([
        for k, g in merge(local.default_groups, try(w.groups, {})) :
        replace(replace(g, "{PREFIX}", upper(w.prefix)), "{prefix}", lower(w.prefix)) if g != null
      ]))
    }
  }
  # Who may see which workspace's rows: the view's row filter.
  access = flatten([for name, m in local.members : [for g in m.groups : { workspace_id = m.id, group = g }]])
  # The groups that open the dashboard. Those of the central workspace itself are already
  # in it (its own baseline manages them); the others get consumer access to it here.
  viewer_groups   = sort(distinct([for a in local.access : a.group]))
  central_ids     = [for name, m in local.members : m.id if trimsuffix(m.host, "/") == trimsuffix(coalesce(local.host, "-"), "/")]
  external_groups = sort(distinct([for a in local.access : a.group if !contains(local.central_ids, a.workspace_id)]))

  # Catalogs this repository manages (authoritative grants): the cost view cannot live in one.
  managed_catalogs = [
    for name, w in local.workspaces :
    replace(replace(try(w.catalog.name, try(yamldecode(file("${local.defaults_dir}/catalog.yaml")).catalog.name, "")), "{PREFIX}", upper(w.prefix)), "{prefix}", lower(w.prefix))
  ]
}
