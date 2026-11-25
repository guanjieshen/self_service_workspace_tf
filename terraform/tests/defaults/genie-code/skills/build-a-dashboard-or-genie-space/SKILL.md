<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/build-a-dashboard-or-genie-space/.
This organization's rules for AI/BI dashboards and Genie spaces; Genie Code knows how to build them.
-->
---
name: build-a-dashboard-or-genie-space
description: "Use when someone wants to see, filter or share numbers and charts (a dashboard, a report, KPIs), or to ask questions of their data in plain language (a Genie space). Says how this organization wants them built: from which tables, on which warehouse, named, tagged and shared so each person sees only their own data. Genie Code knows how to build them."
---

# Build a dashboard or a Genie space the way this workspace wants it

Often the whole answer to "I need an app": suggest it first when people mainly need to look at data. Build from tables in the project's **permanent schema** (a temporary one is deleted with its tables): its **gold tables** (the skill **build-a-pipeline**) or a table you found together (the skill **start-a-project**).

| | The standard |
| --- | --- |
| **Names** | `<prefix>-dashboard-<name>` and `<prefix>-genie-<name>` (`<prefix>` = {PREFIX} in lower case); a title people recognise on the page itself |
| **Where** | The project's folder (`dashboards/`), not their home folder's top level |
| **The warehouse** | The shared `{WAREHOUSE}`: it's already tagged. Never create a warehouse yourself; a team that needs its own asks TIS (the skill **ask-tis**) |
| **Whose data it shows** | **Each viewer's own:** publish without embedded credentials, so everyone sees only what Unity Catalog lets them see. Never share with the owner's credentials |
| **Who can see it** | Share it with Entra ID groups (the team), not one person at a time. Viewers need read access to the tables: if they don't have it, they ask the table's owner |
| **Tags** | The project's tags on the dashboard or Genie space itself (its APPID, `OWNER`), as the skill **build-tagged-assets** says |
| **A dashboard** | A line under the title saying where the data comes from and how fresh it is |
| **A Genie space** | Only the tables it needs, not a whole schema; instructions in the business's own terms; check each sample question's answer with them |

**Before you finish:** open it with them, check each number against something they trust, and add it to the project's `AGENTS.md` (its name, where it is, who it's shared with).
