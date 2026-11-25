<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-tagged-assets/
in every workspace.

- The front matter (between the --- lines) must come first and give name (the
  folder name) and description. Genie Code reads the description to decide when
  to use the skill, so say plainly what it is for.
- Placeholders filled in per workspace: {PREFIX}, {CATALOG}, {WAREHOUSE}, {TAGS} (every chargeback tag), {WORKSPACE_TAGS} (the ones set for you, with their values).
- Comments like this one are removed before deploying.
-->
---
name: build-tagged-assets
description: Use when creating or changing anything that runs on compute or that people use, such as a job, pipeline, cluster, serverless notebook, model serving endpoint, SQL warehouse, app, dashboard or Genie space, so that it carries the tags used for chargeback. Also use when asked why an asset is missing tags or which tags or usage policy to use.
---

# Build assets that carry the chargeback tags

Every asset that uses compute in this workspace is charged back to whoever owns it, using these tags: {TAGS}.

- Set for you on serverless usage, the SQL warehouse and classic clusters: {WORKSPACE_TAGS}.
- On a classic cluster the user also fills in the other tags (for example their team and project), in upper case.

Untagged work can't be charged back, so treat the tags as required, not optional.

## Before you build

1. Find out the owner's value for each tag the user must fill in (team, project). If the user has not said, ask them. Don't guess or make up values.
2. **The APPID:** use the project's (in its `AGENTS.md`, set by the skill start-a-project) if it has its own CMDB application ID; otherwise the workspace's, which the usage policy already adds.
3. Values are upper case letters, digits, `_` and `-`, for example `RISK_CLASSIFICATION`.

## How to tag each kind of asset

- **Serverless notebooks, jobs and pipelines**: select a serverless usage policy. It adds the tags for you. Use the project's policy if the user has one, otherwise `{PREFIX}-0-SELF-SERVICE`. If no usage policy is offered, tag the job or pipeline itself as below.
- **Jobs**: add the tags in the job's tags (`tags` in the job definition). For serverless tasks, also set the usage policy (`budget_policy_id` in the job definition).
- **Classic clusters and job clusters**: create them only from `{PREFIX} Classic Interactive` (all-purpose clusters) or `{PREFIX} Classic Jobs` (job clusters); access comes from their workspace's platform team. The policy sets the fixed tags and asks for the others; fill in the owner's. Don't use the Personal Compute policy for shared or scheduled work, because its clusters don't carry the tags.
- **Pipelines on classic compute**: put the tags in the custom tags of the pipeline's clusters and use the `{PREFIX} Classic Pipelines` cluster policy.
- **Model serving endpoints and other assets that offer tags or a usage policy**: set the usage policy if offered and add the tags.
- **SQL**: use the shared `{WAREHOUSE}` warehouse rather than creating a new one; it's already tagged. Dashboards and Genie spaces are charged through the warehouse they use.
- **Apps, dashboards and Genie spaces**: also tag the asset itself, so people can find whose it is and what it's for: the project's tags (its APPID, `OWNER`), and on an app `LEAVE_ON` (`true` or `false`: ask them; `false` lets the platform team turn it off when it isn't needed). Use the entity tags API: `POST /api/2.0/entity-tag-assignments` with `entity_type` (`apps`, `dashboards` or `geniespaces`), `entity_id` (the app's name, or the dashboard's or space's ID), `tag_key` and `tag_value`.

## Check before you finish

- Show the user the tags and usage policy you set on each asset.
- When you change an existing asset, keep its tags. Don't remove or rename them.
- If you can't set a tag (for example, the policy doesn't offer the user's team), say so and suggest asking the workspace's platform team, rather than leaving the asset untagged.
