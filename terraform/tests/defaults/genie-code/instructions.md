<!--
=============================================================================
GENIE CODE WORKSPACE INSTRUCTIONS: the default for every workspace.

Deployed to /Workspace/.assistant_workspace_instructions.md in each workspace.
A workspace can add its own as text (genie_code_instructions in its
config/workspaces/<name>.yaml); they are appended below these.
Skills (for specific tasks) are in skills/ next to this file.

- Write plain Markdown, as you would brief a new colleague.
- Placeholders filled in per workspace: {PREFIX}, {CATALOG}, {WAREHOUSE}, {TAGS} (every chargeback tag), {WORKSPACE_TAGS} (the ones set for you, with their values).
- Comments like this one are removed before deploying.
- Deployed under the heading "Default instructions"; a workspace's own
  instructions follow under "Workspace instructions". Start sections here at ##.
- Genie Code reads at most 20,000 characters (defaults plus workspace
  instructions); the plan fails if the combined text is longer.
- Workspace admins cannot keep manual edits: the next apply restores this text.
=============================================================================
-->
This is a governed citizen development workspace ({PREFIX}). Follow these conventions in everything you suggest or generate.

## Data

- Work with data in Unity Catalog. The workspace's catalog is `{CATALOG}`.
- By default, create your tables, views and volumes in your **personal schema** in `{CATALOG}`, and read and write there unless asked otherwise. The self-service app creates it when you request one: `cd_` followed by your email name, with any character other than a letter or digit as `_` (`jane.doe@...` gets `{CATALOG}.cd_jane_doe`, with a short suffix if that name was taken). If you do not have one yet, suggest requesting it in the self-service app. Use a team or shared schema only for work the team shares, and do not create schemas yourself: they come from the self-service app.
- Always use three-part names (`catalog.schema.table`). Do not use the Hive metastore, DBFS paths or DBFS mounts; they are switched off or being retired.
- Do not copy data out of Unity Catalog into files, notebooks or personal storage. Read it where it is.
- Never put credentials, passwords, tokens or keys in code. Use Databricks secrets or the identity the job runs as.

## Compute

- For SQL, use the `{WAREHOUSE}` SQL warehouse.
- For notebooks, jobs and pipelines, prefer serverless compute.
- Classic compute is the exception. When it is needed, use the classic cluster policy for the kind of cluster: `{PREFIX} Classic Interactive` for notebooks, `{PREFIX} Classic Jobs` for job clusters, `{PREFIX} Classic Pipelines` for pipelines (access is requested through the self-service app). Each sets the tags and limits, and asks for the tags you fill in; each allows one cluster per person.
- Avoid the Personal Compute policy for shared or scheduled work: its clusters do not carry the chargeback tags.

## Cost attribution

- Every workload is charged back with the tags {TAGS}. Set for you: {WORKSPACE_TAGS}. Keep the tags on any cluster or job you define.
- For serverless jobs, pipelines and notebooks, select a serverless usage policy: `{PREFIX}-0-SELF-SERVICE` for general work, or your project's policy if you have one.

## Sharing work

- Keep work in progress in your own folder.
- Put finished work that your team should use in your team's folder (`/Workspace/<team>`), if the self-service app created one.
- Name notebooks, jobs and dashboards after what they do, and add a short description of their purpose and owner.
