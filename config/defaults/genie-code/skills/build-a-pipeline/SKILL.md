<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-a-pipeline/. This
organization's rules for pipelines; Genie Code already knows how to build Lakeflow pipelines.
-->
---
name: build-a-pipeline
description: Use when someone needs data loaded, cleaned, joined or kept up to date for their work: a pipeline, an ETL, ingestion, "refresh this every morning", a bronze, silver or gold table. Says how this organization wants pipelines built (where the tables go, names, compute, tags, schedule, secrets, data quality, when to ask TIS); Genie Code knows how to write the Lakeflow pipeline itself.
---

# Build a pipeline the way this workspace wants it

Build it as a **Lakeflow Spark Declarative Pipeline** (SQL unless they need Python), in the project's `pipeline/` folder (the skill **start-a-project**). These are the rules; how to write it is yours.

| | The standard |
| --- | --- |
| **Layers** | Bronze (as it arrived), silver (cleaned, typed, deduplicated), gold (what the dashboard, Genie space or app reads). Small projects may skip bronze |
| **Where the tables go** | Their **temporary schema** while they try it (30 days; their Azure PIM account), then the project's **permanent schema** (requested in the self-service app) to keep it. Never another person's schema, never a production schema |
| **Names** | The pipeline `<prefix>-pipeline-<name>`, its job `<prefix>-job-<name>` (`<prefix>` = {PREFIX} in lower case); tables `bronze_<thing>`, `silver_<thing>`, `gold_<thing>`, each with a one-line comment |
| **Compute** | **Serverless**, with the usage policy `{PREFIX}-0-SELF-SERVICE` (or the project's): it charges the work to the right business unit. Never classic compute unless TIS has given them access |
| **Tags** | The policy adds this workspace's ({WORKSPACE_TAGS}). The project's own APPID, if it has one, on the pipeline and its job as well (the skill **build-tagged-assets**) |
| **Schedule** | **Triggered** (never continuous unless TIS agrees), run by its job on a schedule they choose: daily by default. Ask when the data should be fresh by |
| **Data quality** | An expectation for each rule the data must meet (not null, valid values, in range): drop bad rows in silver, fail the update for what must never happen. Tell them what each one checks |
| **Secrets** (an API key, a password) | A **Unity Catalog secret** in the project's permanent schema (Catalog Explorer > the schema > Create > Secret), read with `dbutils.secrets.get(catalog=..., schema=..., key=...)`. Never in code, a notebook or a table |

**Ask TIS (the skill ask-tis) for:** a connection to another system (a database, SharePoint, an outside API), network access, a service principal, or a production source. Don't work around a missing connection by copying files by hand.

**Before you finish:** run it once, show them each table's row count and the expectations' results, name the schedule, and add the pipeline to the project's `AGENTS.md`.
