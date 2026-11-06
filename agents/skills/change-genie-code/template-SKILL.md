<!--
DEFAULT GENIE CODE SKILL: copy to config/defaults/genie-code/skills/<name>/SKILL.md, where
<name> is lowercase words and dashes, and the same as name below. Deployed to
/Workspace/.assistant/skills/<name>/ in every workspace.

- The front matter (between the --- lines) comes first. description starts with "Use when"
  and says plainly when to use the skill: Genie Code matches requests against it.
- Placeholders, filled in per workspace: {PREFIX}, {CATALOG}, {WAREHOUSE}, {WAREHOUSE_DETAILS},
  {TAGS}, {WORKSPACE_TAGS}, {PERSONAS}, {CLASSIC_POLICIES} (config/README.md).
- House style (agents/skills/change-genie-code): warm, plain and short; help, don't block;
  say only what's true in this workspace; no em dashes.
- Comments like this one are removed before deploying.
-->
---
name: <name>
description: Use when someone <what they ask for, in their words>. <What this skill helps them do, in one sentence.>
---

# <What it helps with, in plain words>

<One or two sentences: what this is for, and who usually asks.>

## Before you start

- <What to check or ask first, at most two questions at a time.>

## Steps

1. <One step at a time, in plain words. Where to click before code.>
2. <...>

## Check before you finish

- <What to show or confirm with the person.>
- Offer the one next step that would help most.
