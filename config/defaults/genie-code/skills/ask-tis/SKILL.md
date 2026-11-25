<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/ask-tis/. Works out what someone
needs from TIS, sends them to the right place for it, and records it in the project.
-->
---
name: ask-tis
description: Use when someone needs something they can't or shouldn't make themselves in this workspace: a schema to keep their work, more time for a temporary schema, a workspace folder, a group to share with, workspace access, a domain, access to a table, a production dataset, a connection to another system, network access to an outside service or API, a service principal, classic compute, or anything a check refused for lack of permission. Works out what they need, sends them to the right place (the self-service app, the table's owner, their platform team, or a request to TIS), and records it in the project's AGENTS.md.
---

# Ask TIS

TIS (the platform team) provides what people don't make themselves. Each thing has one right place to ask: find out what they need, then send them there.

## 1. What do they need?

Often they say what they're stuck on ("it says permission denied", "I need the SAP data"), not what to ask for. Work it out with them, in plain words:

- **What they're trying to do,** and what stopped them (the error, if there is one).
- **The exact thing:** which table, system, schema, folder or group; read only, or changing it too.
- **For what:** the project (`<prefix>-<project>`), its APPID, who else will use it.

If they don't need TIS after all (the table is there and they can read it, the error was a typo), say so and carry on.

## 2. Send them to the right place

| They need | Where | What happens |
| --- | --- | --- |
| A schema to **keep** a project's or team's work | Self-service app: **Request a permanent schema** (add the team's Entra ID group for a team schema) | A person approves it |
| A place to **try things** | Self-service app: **Create a temporary schema**, signed in with their Azure PIM account (`azure-...`, their admin account for Azure). One per person at a time | Made straight away; deleted with its contents on its `cd_expires` date |
| **More time** for their temporary schema | Self-service app: **Extend temporary schema** | Straight away |
| A **workspace folder** for a team | Self-service app: **Request a workspace folder** | A person approves it; an admin makes it |
| A group in the workspace, **to share folders with** | Self-service app: **Add a group to your workspace** | The admin team approves it |
| **Workspace access**, or a different persona (Explorer, Builder, Publisher) | Self-service app: **Request workspace access** (Explorer with their regular account; Builder and Publisher with their Azure PIM account) | A person approves it |
| **A domain** | Self-service app: **Request a domain** | While its tile says Coming soon: a request to TIS |
| **Read access to a table** that exists | Its owner: Catalog Explorer > the table > **Request access** | The owner decides. Not TIS |
| A production dataset, a connection to another system, network access, a service principal, classic compute | **A request to TIS** (section 3) | TIS decides and tells them |

In the self-service app, help them fill in the form: the name, the reason in a sentence, the group. If its tile says **Coming soon**, or the app refuses, write a request to TIS instead.

## 3. A request to TIS

Write it for them to send, short and complete:

```
What: <the thing, exactly: the table, the system and its address, the access level>
Why: <the business reason, in a sentence or two>
For: <the project (<prefix>-<project>), its APPID, who will use it>
When: <when they need it, and what waits on it>
Details: <anything TIS will ask: the data's sensitivity, how often, who owns the other system>
```

Never put a password or a key in it: TIS tells them how to hand a secret over. Ask how their team reaches TIS if you don't know.

## 4. Record it

Add a row to the project's `AGENTS.md`, under **Asked of TIS**: the date, what was asked, where (the app, the owner, or a request), and its status. Update it when it's answered, so the next session knows what is waiting.
