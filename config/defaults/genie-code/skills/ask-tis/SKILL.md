<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/ask-tis/. Writes the request
when someone needs something the platform team (TIS) provides, and records it in the project.
-->
---
name: ask-tis
description: Use when someone needs something they can't or shouldn't do themselves in this workspace: a permanent schema, access to a workspace or a folder group, a production dataset, a connection to another system, network access to an outside service or API, a service principal, classic compute, or anything a check refused for lack of permission. Says where to ask (the self-service app first) and writes the request, ready to send, then records it in the project's AGENTS.md.
---

# Ask TIS

TIS (the platform team) provides what citizen developers don't make themselves. Help them ask once, clearly, in the right place, and keep a record.

## 1. Where to ask

| They need | Ask in |
| --- | --- |
| A **permanent schema** (project or team) | The self-service app: **Request a permanent schema** |
| More time for a **temporary schema** | The self-service app: **Extend temporary schema** (no approval) |
| A **workspace folder** | The self-service app: **Request a workspace folder** |
| A group added to the workspace, **to share folders with** | The self-service app: **Add a group to your workspace** |
| **Workspace access** (Explorer, Builder, Publisher) | The self-service app: **Request workspace access** (Builder and Publisher with their Azure PIM account) |
| **A domain** | The self-service app: **Request a domain** (coming soon: until then, as below) |
| Anything else: a production dataset, a connection, network access, a service principal, classic compute | The request below, sent to TIS (a request form for these is being set up) |

## 2. Write the request

For anything not in the self-service app, write it for them to send, short and complete:

```
What: <the thing, exactly: the table, the system and its address, the access level>
Why: <the business reason, in a sentence or two>
For: <the project (<prefix>-<project>), its APPID, who will use it>
When: <when they need it, and what waits on it>
Details: <anything TIS will ask: the data's sensitivity, how often, who owns the other system>
```

Never put a password or a key in it: TIS tells them how to hand a secret over.

## 3. Record it

Add a row to the project's `AGENTS.md`, under **Asked of TIS**: the date, what was asked, where (the app, or the request), and its status. Update it when TIS answers, so the next session knows what is waiting.
