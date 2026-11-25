<!--
DEFAULT GENIE CODE SKILL: deployed to /Workspace/.assistant/skills/plan-a-databricks-app/ in every
workspace. The interview before an app is built; build-a-databricks-app builds it.
-->
---
name: plan-a-databricks-app
description: Use when someone wants an app, a tool or a "system" for their work but hasn't said exactly what it does, or says what they want in business terms (a process, a decision, a spreadsheet they want to replace). Interviews them in plain words about the problem, the people, the decisions and the data, checks whether a dashboard or a Genie space would serve them better, and turns the answers into the brief the skill build-a-databricks-app builds from.
---

# Plan an app with someone

The people who ask for apps here know their business deeply and are usually not software engineers. Your job in this skill is to **understand the work before you build anything**, in their words, then hand a clear brief to the skill **build-a-databricks-app**.

## How to talk

- **Their words, not ours.** Ask about their work, their decisions and their people. Never ask them to choose a technology. Say "a page", "a form", "a list", "saved", not React, API, Lakebase or schema.
- **Two questions at a time at most,** each with a suggested answer or two examples they can pick from ("For example: a weekly review of overdue work orders, or a form where field teams log inspections").
- **Show you understood:** play back what you heard in a sentence before the next question.
- **Short.** Three or four rounds is plenty: once you could describe the app to a colleague, stop and write the brief.

## 1. The work

| Ask about | Listen for |
| --- | --- |
| **What happens today:** the task, the spreadsheet, the email chain or the report it would replace | The pain: what is slow, manual, error-prone or invisible |
| **Who** does it, and who else needs to see it | The users, and the people who only look |
| **The decision or action** the app should help with ("decide which wells to inspect first") | What the first screen must show |
| **What "better" looks like:** time saved, fewer mistakes, a decision made sooner | How they'll know it works; what to build first |

## 2. Is an app the right tool?

Before you plan an app, check whether something simpler does the job, and say so plainly:

| If they need | Suggest |
| --- | --- |
| Charts and numbers to look at, filter and share | An **AI/BI dashboard**: faster to make and to change |
| To ask questions of their data in plain language | A **Genie space** |
| To **do** something: record, update, approve, assign, track a status, combine data with what people type | **An app**: carry on |

## 3. The data

- **What it reads:** which data they look at today. Help them find it: search the catalog (start with `{CATALOG}`), check each table you find with `DESCRIBE TABLE`, and confirm with them that it's the right one ("This table has one row per work order, with its due date and status: is this what you use?"). Note each table's full name.
- **What it keeps:** what people would type or change in the app (notes, statuses, assignments, approvals). That becomes the app's own data. Nothing: the app only shows data.
- **Who may see what:** the app shows each person only the data they can already read. If someone who'll use it can't read a table, they ask its owner for access (Catalog Explorer > Request access).

## 4. The brief

When you can describe the app, write the brief **as a short summary for them** (their words), then the skill **build-a-databricks-app** takes over (step 1 there turns it into the build brief, with the app's name and folder):

```
App: <a short name>: <what it helps them do, one sentence>
For: <who uses it>; <who only looks>
Screens: <two to four: what each shows, and what people do there>
Reads: <each table's full name: what from it>
Keeps: <what people type or change, or "nothing">
First version: <the smallest useful thing; what comes later>
```

Ask "Is this what you need?" and change it until they say yes. Keep the brief: it goes into the app's `AGENTS.md` and `README.md`, so the next person (or Genie Code session) knows why the app is the way it is.
