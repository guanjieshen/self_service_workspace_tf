<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/how-this-workspace-works/
in every workspace. Terraform fills in the placeholders from this workspace's configuration
({PERSONAS}, {CLASSIC_POLICIES}, {WAREHOUSE_DETAILS}, and the usual {PREFIX}, {CATALOG},
{WAREHOUSE}, {TAGS}, {WORKSPACE_TAGS}), so it always describes the workspace it is in.
Comments like this one are removed before deploying.
-->
---
name: how-this-workspace-works
description: Use when someone asks what they can do in this workspace, why they can't do something (open a notebook, create a schema, start a cluster), which compute or warehouse to use, what the limits are, or how to get more access or resources.
---

# How this workspace works

This is a governed self-service workspace. Most of it is set up for people already: the data catalog, a shared SQL warehouse, compute policies and the tags that charge usage back. People get more (schemas, access) by asking, not by building it themselves.

Use it to explain what someone can do and how to get what they need. Keep it short: answer their question, bring in only what helps, and offer the next step.

## Who can do what

Access comes from a **persona**, which a person gets by being in its group. In this workspace:

{PERSONAS}

If someone can't do something, it's usually their persona: say which persona would let them, and that they ask for it in the self-service app (Request workspace access). Never suggest a workaround. Don't name groups; say the persona.

## Data

- **The workspace's catalog is `{CATALOG}`**, and it's the default: a table name without a catalog means `{CATALOG}`.
- **Each person may have a temporary schema** there to try things, created in the self-service app (`cd_tmp_<name>`): their Azure PIM account reads and writes it, their regular account reads it. It's **deleted with its contents** on the date in its `cd_expires` tag, unless they extend it.
- **Permanent schemas** keep a project's work, alone or with a team. People request them in the self-service app, and a person approves the request.
- **Nobody creates schemas by hand.** They come from the self-service app.

## Compute

- **SQL:** the shared warehouse, `{WAREHOUSE}` ({WAREHOUSE_DETAILS}). It's the default for queries, dashboards and Genie spaces.
- **Notebooks, jobs and pipelines:** serverless, with the `{PREFIX}-0-SELF-SERVICE` usage policy (or a project's policy). The policy adds this workspace's tags: {WORKSPACE_TAGS}.
- **Classic clusters** are the exception, and only through these policies:

{CLASSIC_POLICIES}

  Nobody can use them until their workspace's platform team gives them access. On a classic cluster, people fill in the chargeback tags ({TAGS}) the policy asks for.

## Getting more

| Someone needs | How they get it |
| --- | --- |
| A schema to try things | Create a temporary schema in the self-service app |
| A schema for their team or project | Request it in the self-service app; a person approves it |
| A different persona (for example to open notebooks) | Request workspace access in the self-service app; a person approves it |
| Classic compute | Ask their workspace's platform team |
| Access to data someone else owns | Ask the data's owner, in Catalog Explorer (Request access) |
