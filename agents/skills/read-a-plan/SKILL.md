---
name: read-a-plan
description: Use when someone asks what a pull request will do, whether it is safe to merge, or what a plan comment means ("is this safe?", "what does this change?", "what is Before merging?"). Explains the plan comment of each workspace and the App plan in plain words, especially what the plan guard lists under Before merging, and ends with a clear recommendation: safe to merge, or ask someone first. Never merges.
---

# Read a plan

A **plan** is what GitHub Actions says a change **will** do in each workspace, before anything happens. Your job is to say it in plain words and flag what needs a person's decision. Merging is done by a code owner through the skill **pull-request-from-databricks**; you never merge.

## 1. Find it

On the pull request, each workspace the change concerns has a comment **Plan: `<workspace>`**, and the app has **App plan**. Each starts with a risk summary and a table of what changes.

## 2. Say what changes, per workspace

For each comment: **how many things are added, changed and deleted**, and what they are in plain words ("the `hr` workspace's SQL warehouse becomes Medium"; "two group assignments are removed"). Compare it with what the pull request says it does: anything extra is a question for its author.

## 3. Before merging: what needs a person

The plan guard lists, under **Before merging**, anything that is:

| Kind | What it means | Ask |
| --- | --- | --- |
| **Removes access** | People or groups lose a permission or entitlement | Did they mean to? Who is affected? |
| **Weakens security** | A security setting is loosened (for example tokens allowed longer) | Did the security reviewer agree? |
| **Hard to undo** | Something is deleted or replaced (a catalog, a usage policy, a workspace setting) | Is the data or setting safe to lose? |

## 4. Recommend

End with one of:
- **Safe to merge:** only what the pull request says, nothing under Before merging.
- **Ask someone first:** name who (the author, a platform admin, security) and the exact question.

A failed plan is not a plan to read: hand over to the skill **fix-a-failed-check-or-deploy**.
