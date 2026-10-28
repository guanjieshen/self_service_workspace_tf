<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-tagged-assets/
in every workspace.

- The front matter (between the --- lines) must come first and give name (the
  folder name) and description. Genie Code reads the description to decide when
  to use the skill, so say plainly what it is for.
- Placeholders filled in per workspace: {BU}, {LOB}, {CATALOG}, {WAREHOUSE}.
- Comments like this one are removed before deploying.
-->
---
name: build-tagged-assets
description: Use when creating or changing anything that runs on compute, such as a job, pipeline, cluster, serverless notebook, model serving endpoint or SQL warehouse, so that it carries the LOB, DEPARTMENT and TEAM tags used for chargeback. Also use when asked why an asset is missing tags or which tags or usage policy to use.
---

# Build assets that carry the chargeback tags

Every asset that uses compute in this workspace is charged back to whoever owns it, using three tags:

| Tag | Value |
|-----|-------|
| `LOB` | `{LOB}` (the same for everything in this workspace) |
| `DEPARTMENT` | The owner's department |
| `TEAM` | The owner's team |

Untagged work cannot be charged back, so treat the tags as required, not optional.

## Before you build

1. Find out the DEPARTMENT and TEAM the work belongs to. If the user has not said, ask them. Do not guess or make up values.
2. Shared work that belongs to no one team uses `DEPARTMENT: SHARED` and `TEAM: SHARED`.

## How to tag each kind of asset

- **Serverless notebooks, jobs and pipelines**: select a serverless usage policy. It adds the tags for you. Use `{BU}-SHARED`. If no usage policy is offered, tag the job or pipeline itself as below.
- **Jobs**: add the three tags in the job's tags (`tags` in the job definition). For serverless tasks, also set the usage policy (`budget_policy_id` in the job definition).
- **Classic clusters and job clusters**: create them only from the user's persona cluster policy (`{BU} <Persona> Compute`). The policy sets `LOB` and asks for allowed `DEPARTMENT` and `TEAM` values; choose the owner's. Do not use the Personal Compute policy for shared or scheduled work, because its clusters do not carry the tags.
- **Pipelines on classic compute**: put the three tags in the custom tags of the pipeline's clusters and use the persona cluster policy.
- **Model serving endpoints and other assets that offer tags or a usage policy**: set the usage policy if offered and add the three tags.
- **SQL**: use the existing `{WAREHOUSE}` warehouse (or the team's warehouse) rather than creating a new one; those warehouses are already tagged. Dashboards and Genie spaces are charged through the warehouse they use.

## Check before you finish

- Show the user the tags and usage policy you set on each asset.
- When you change an existing asset, keep its tags. Do not remove or rename them.
- If you cannot set a tag (for example, the policy does not offer the user's team), say so and suggest asking the workspace's platform team, rather than leaving the asset untagged.
