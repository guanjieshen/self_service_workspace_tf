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

  # Sharing groups: assigned only so people can share with them, with no entitlements.
  sharing_groups = distinct([for g in coalesce(try(local.config.sharing_groups, null), []) : replace(replace(g, "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)])

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
  # Each principal's privileges from every source, together: a persona group named in
  # other_privileges keeps its persona privileges and gets the extra ones too.
  catalog_grant_pairs = concat(
    [for g in distinct(flatten(values(local.persona_groups))) : { principal = g, privileges = try(local.config.catalog.persona_privileges, []) }],
    [for g in local.platform_admins : { principal = g, privileges = try(local.config.catalog.platform_admin_privileges, []) }],
    # Anyone else: an application ID or a group name, or a key of groups.
    [for p, privs in coalesce(try(local.config.catalog.other_privileges, null), {}) : { principal = lookup(local.group_names, p, p), privileges = privs }],
    # The self-service app's service principals (self_service.tf): they see the catalog.
    [for id in local.self_service_app_ids : { principal = id, privileges = ["USE_CATALOG", "BROWSE"] }],
  )
  catalog_grants = {
    for principal in distinct([for x in local.catalog_grant_pairs : x.principal]) : principal => sort(distinct(flatten([
      for x in local.catalog_grant_pairs : x.privileges if x.principal == principal
    ])))
  }
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

  # Instructions: the default, then the organization's business context (genie-code/
  # our-business.md, while it holds more than comments), then this workspace's own, each under
  # a heading, with <!-- comments --> removed.
  genie_default_text   = try(trimspace(replace(file("${local.genie_default_dir}/instructions.md"), "/(?s)<!--.*?-->/", "")), "")
  genie_business_text  = try(trimspace(replace(file("${local.genie_default_dir}/our-business.md"), "/(?s)<!--.*?-->/", "")), "")
  genie_workspace_text = trimspace(replace(try(tostring(local.ws_all.genie_code_instructions), ""), "/(?s)<!--.*?-->/", ""))
  genie_parts = compact([
    local.genie_default_text == "" ? "" : "# Default instructions\n\nShared by every citizen development workspace.\n\n${local.genie_default_text}",
    local.genie_business_text == "" ? "" : "# About our business\n\n${local.genie_business_text}",
    local.genie_workspace_text == "" ? "" : "# Workspace instructions\n\nFor this workspace only${local.genie_default_text == "" ? "" : ", in addition to the default instructions"}.\n\n${local.genie_workspace_text}",
  ])

  # ---- The placeholders, filled in from this workspace's configuration ----
  # {TAGS}: every chargeback tag; {WORKSPACE_TAGS}: the ones set for you, with their values.
  genie_tags           = join(", ", [for t in local.all_tag_keys : "`${t}`"])
  genie_workspace_tags = length(local.chargeback_tags) == 0 ? "none" : join(", ", [for k, v in local.chargeback_tags : "`${k}` = `${v}`"])
  # {PERSONAS}: the personas this workspace has (a group named for them), and what each can do.
  genie_tier_text = {
    consumer  = "Databricks One: dashboards, Genie spaces and apps others share",
    sql       = "SQL: Databricks One, plus the SQL editor, queries, dashboards and Genie spaces",
    workspace = "the full workspace: notebooks, jobs and pipelines, plus everything SQL can do",
  }
  genie_personas = join("\n", concat(
    local.users_group == null ? [] : ["- **Everyone in the workspace**: ${lookup(local.genie_tier_text, try(local.config.users.access, "consumer"), local.genie_tier_text.consumer)}."],
    [for p in sort(keys(local.persona_groups)) : "- **${title(p)}**: ${lookup(local.genie_tier_text, try(local.personas[p].access, "consumer"), local.genie_tier_text.consumer)}."],
    length(local.persona_groups) == 0 && local.users_group == null ? ["- No personas are set up in this workspace yet."] : [],
  ))
  # {CLASSIC_POLICIES}: each classic cluster policy this workspace has, with its limits.
  genie_policy_kinds = { interactive = "all-purpose clusters, for notebooks", jobs = "job clusters", pipelines = "pipeline clusters" }
  genie_cp           = try(local.config.cluster_policy, null)
  genie_classic = join("\n", concat([
    for k in ["interactive", "jobs", "pipelines"] : join("", [
      "  - `${replace(replace(local.genie_cp[k].name, "{PREFIX}", local.prefix_upper), "{prefix}", local.prefix)}`: ${local.genie_policy_kinds[k]}",
      "; up to ${try(local.genie_cp[k].max_clusters_per_user, 1)} at a time per person",
      ", up to ${try(local.genie_cp[k].max_workers, local.genie_cp.max_workers)} workers",
      try(local.genie_cp[k].max_autotermination_minutes, null) == null ? "" : ", stopping after at most ${local.genie_cp[k].max_autotermination_minutes} idle minutes",
      length(try(local.genie_cp.node_types, [])) == 0 ? "" : ", on ${join(", ", [for n in local.genie_cp.node_types : "`${n}`"])}",
      ".",
    ]) if try(local.genie_cp[k], null) != null
    ], try(length([for k in ["interactive", "jobs", "pipelines"] : k if try(local.genie_cp[k], null) != null]), 0) == 0 ? ["  - None in this workspace."] : []
  ))
  # {WAREHOUSE_DETAILS}: the shared warehouse's size and auto-stop.
  genie_warehouse_details = join(", ", compact([
    try(local.config.sql_warehouse.size, null) == null ? "" : "size ${local.config.sql_warehouse.size}",
    try(local.config.sql_warehouse.auto_stop_minutes, null) == null ? "" : "stops after ${local.config.sql_warehouse.auto_stop_minutes} idle minutes",
  ]))

  # Skills: one folder per skill under genie-code/skills/, each with a SKILL.md. The baseline's,
  # plus this workspace's own (config/workspaces/<workspace>/genie-code/skills/); a workspace skill
  # with a baseline skill's name replaces it, in this workspace.
  genie_ws_skills_dir    = "${local.workspaces_dir}/${var.workspace}/genie-code/skills"
  genie_skill_files      = [for f in fileset("${local.genie_default_dir}/skills", "*/**") : f if !startswith(basename(f), ".")]
  genie_ws_skill_files   = [for f in fileset(local.genie_ws_skills_dir, "*/**") : f if !startswith(basename(f), ".")]
  genie_ws_skill_folders = distinct([for f in local.genie_ws_skill_files : split("/", f)[0]])
  genie_skill_sources = merge(
    { for f in local.genie_skill_files : f => "${local.genie_default_dir}/skills/${f}" if !contains(local.genie_ws_skill_folders, split("/", f)[0]) },
    { for f in local.genie_ws_skill_files : f => "${local.genie_ws_skills_dir}/${f}" },
  )

  # Every text Genie Code gets (the instructions, and each skill's Markdown), rendered the same way.
  genie_raw = merge(
    { "" = join("\n\n", local.genie_parts) },
    { for f, src in local.genie_skill_sources : f => trimspace(replace(file(src), "/(?s)<!--.*?-->/", "")) if endswith(f, ".md") },
  )
  genie_rendered = {
    for k, t in local.genie_raw : k => replace(replace(replace(replace(replace(replace(replace(replace(t,
      "{PREFIX}", local.prefix_upper),
      "{CATALOG}", local.genie_catalog),
      "{WAREHOUSE_DETAILS}", local.genie_warehouse_details),
      "{WAREHOUSE}", local.genie_warehouse),
      "{WORKSPACE_TAGS}", local.genie_workspace_tags),
      "{TAGS}", local.genie_tags),
      "{PERSONAS}", local.genie_personas),
    "{CLASSIC_POLICIES}", local.genie_classic)
  }
  genie_instructions = length(local.genie_parts) == 0 ? null : local.genie_rendered[""]
  # Markdown gets the same treatment as the instructions; other files are deployed as they are.
  genie_skill_text = { for f in keys(local.genie_skill_sources) : f => local.genie_rendered[f] if endswith(f, ".md") }
  genie_skills = {
    for f, src in local.genie_skill_sources : f => (
      endswith(f, ".md")
      ? base64encode("${local.genie_skill_text[f]}\n")
      : filebase64(src)
    )
  }
}
