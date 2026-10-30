# Which group holds each persona, and what each group gets on shared objects.
# Everything is granted to groups; who is in them is managed in Entra ID.

locals {
  # ---- The groups (groups: in the baseline and the workspace's file), with {prefix} / {PREFIX} filled in ----
  group_names = {
    for k, g in local.config.groups : k => replace(replace(g, "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix) if g != null
  }
  persona_groups  = { for p in keys(local.personas) : p => [local.group_names[p]] if contains(keys(local.group_names), p) }
  platform_admins = compact([try(local.group_names.platform_admins, "")])
  users_group     = try(local.group_names.users, null)

  # The users group is assigned to the workspace like the persona groups.
  extra_groups = compact([local.users_group == null ? "" : local.users_group])

  # ---- Entitlements: an access tier per persona (and for the users group) ----
  access_tiers = {
    consumer  = { workspace_access = false, workspace_consume = true, databricks_sql_access = false, allow_cluster_create = false }
    sql       = { workspace_access = false, workspace_consume = false, databricks_sql_access = true, allow_cluster_create = false }
    workspace = { workspace_access = true, workspace_consume = false, databricks_sql_access = true, allow_cluster_create = false }
  }
  entitlement_personas = merge(
    { for p, d in local.personas : p => { entitlements = try(local.access_tiers[d.access], local.access_tiers.consumer) } },
    local.users_group == null ? {} : { users = { entitlements = try(local.access_tiers[local.config.users.access], local.access_tiers.consumer) } },
  )
  entitlement_groups = merge(local.persona_groups, local.users_group == null ? {} : { users = [local.users_group] })

  # ---- The default warehouse's permission, per persona group ----
  # A group in several personas gets the highest permission any of them grants.
  permission_rank = { CAN_VIEW = 1, CAN_MONITOR = 2, CAN_USE = 3, CAN_MANAGE = 4 }
  warehouse_grants = flatten([
    for p, gs in local.persona_groups : [
      for g in gs : { group = g, level = local.personas[p].default_warehouse }
    ] if try(local.personas[p].default_warehouse, null) != null
  ])
  warehouse_acl = {
    for g in distinct([for x in local.warehouse_grants : x.group]) : g => [
      for level, rank in local.permission_rank : level
      if rank == max([for x in local.warehouse_grants : local.permission_rank[x.level] if x.group == g]...)
      && contains([for x in local.warehouse_grants : x.level if x.group == g], level)
    ][0]
  }

  token_groups = distinct(flatten([
    for p, gs in local.persona_groups : gs if try(local.personas[p].can_create_tokens, false) == true
  ]))

  # ---- Unity Catalog: the workspace's catalog (config/defaults/catalog.yaml) ----
  # The owner can be a key of groups (platform_admins, ...) or a group name.
  catalog = local.config.catalog == null ? null : merge(local.config.catalog, {
    name  = replace(replace(local.config.catalog.name, "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)
    owner = try(local.config.catalog.owner, null) == null ? null : lookup(local.group_names, local.config.catalog.owner, local.config.catalog.owner)
  })
  catalog_grants = merge(
    { for g in distinct(flatten(values(local.persona_groups))) : g => sort(try(local.config.catalog.persona_privileges, [])) },
    { for g in local.platform_admins : g => sort(try(local.config.catalog.platform_admin_privileges, [])) },
  )
  default_catalog = try(replace(replace(local.config.default_catalog, "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix), null)

  # ---- Genie Code: workspace instructions and skills ----
  # The baseline's (config/defaults/genie-code/), the same in every workspace, plus a
  # workspace's own instructions as text (genie_code_instructions in its file).
  genie_default_dir = "${local.defaults_dir}/genie-code"
  # settings.genie_code in config/defaults/settings.yaml: true = deploy, null = leave alone.
  manage_genie_instructions = try(local.settings.genie_code.instructions, null) == true
  manage_genie_skills       = try(local.settings.genie_code.skills, null) == true

  genie_catalog   = coalesce(try(local.catalog.name, null), local.default_catalog, "the workspace's catalog")
  genie_warehouse = replace(replace(try(local.config.sql_warehouse.name, "the default warehouse"), "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)

  # Instructions: the default followed by this workspace's own, with <!-- comments -->
  # removed, each under a heading.
  genie_default_text   = try(trimspace(replace(file("${local.genie_default_dir}/instructions.md"), "/(?s)<!--.*?-->/", "")), "")
  genie_workspace_text = trimspace(replace(try(tostring(local.ws_all.genie_code_instructions), ""), "/(?s)<!--.*?-->/", ""))
  # {TAGS}: every chargeback tag; {WORKSPACE_TAGS}: the ones set for you, with their values.
  genie_tags           = join(", ", [for t in local.all_tag_keys : "`${t}`"])
  genie_workspace_tags = length(local.chargeback_tags) == 0 ? "none" : join(", ", [for k, v in local.chargeback_tags : "`${k}` = `${v}`"])
  genie_parts = compact([
    local.genie_default_text == "" ? "" : "# Default instructions\n\nShared by every citizen development workspace.\n\n${local.genie_default_text}",
    local.genie_workspace_text == "" ? "" : "# Workspace instructions\n\nFor this workspace only${local.genie_default_text == "" ? "" : ", in addition to the default instructions"}.\n\n${local.genie_workspace_text}",
  ])
  genie_instructions = length(local.genie_parts) == 0 ? null : replace(replace(replace(replace(replace(
    join("\n\n", local.genie_parts),
    "{PREFIX}", local.prefix_upper),
    "{CATALOG}", local.genie_catalog),
    "{WAREHOUSE}", local.genie_warehouse),
    "{WORKSPACE_TAGS}", local.genie_workspace_tags),
  "{TAGS}", local.genie_tags)

  # Skills: one folder per skill under genie-code/skills/, each with a SKILL.md.
  genie_skill_files   = [for f in fileset("${local.genie_default_dir}/skills", "*/**") : f if !startswith(basename(f), ".")]
  genie_skill_sources = { for f in local.genie_skill_files : f => "${local.genie_default_dir}/skills/${f}" }
  # Markdown gets the same treatment as the instructions; other files are deployed as they are.
  genie_skill_text = {
    for f, src in local.genie_skill_sources : f => replace(replace(replace(replace(replace(
      trimspace(replace(file(src), "/(?s)<!--.*?-->/", "")),
      "{PREFIX}", local.prefix_upper),
      "{CATALOG}", local.genie_catalog),
      "{WAREHOUSE}", local.genie_warehouse),
      "{WORKSPACE_TAGS}", local.genie_workspace_tags),
    "{TAGS}", local.genie_tags) if endswith(f, ".md")
  }
  genie_skills = {
    for f, src in local.genie_skill_sources : f => (
      endswith(f, ".md")
      ? base64encode("${local.genie_skill_text[f]}\n")
      : filebase64(src)
    )
  }
}
