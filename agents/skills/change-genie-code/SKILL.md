---
name: change-genie-code
description: Use when someone wants to add, change or remove a Genie Code skill that every workspace gets, or change Genie Code's default instructions or the business context (about our business). Explains where each lives, the placeholders filled in per workspace, the house style, and hands over to pull-request-from-databricks.
---

# Change Genie Code's instructions and skills

The person may not know Markdown or this repository. Ask what they want Genie Code to do differently, in their own words, then find the right place for it. At most two questions at a time.

## 1. Pick the right place

| They want Genie Code to | Where it goes |
| --- | --- |
| Follow a rule on **every** answer (a convention, a guardrail) | `config/defaults/genie-code/instructions.md`: the default instructions, in every workspace |
| Know about **the organization** (what it does, business units, terms, key data) | `config/defaults/genie-code/our-business.md`, shown as **About our business** |
| Know how to do **one kind of task**, step by step (only when it comes up) | A skill: a new folder in `config/defaults/genie-code/skills/` |
| Behave differently in **one workspace** only | `genie_code_instructions` in that workspace's file (the skill **change-one-workspace**) |

Prefer a skill for anything long or task-specific: the instructions apply to every answer and share a 20,000-character limit (the plan fails above it), while a skill is read only when its description matches the request.

## 2. Write it

- **A new skill:** copy `agents/skills/change-genie-code/template-SKILL.md` to `config/defaults/genie-code/skills/<name>/SKILL.md`. The folder name is lowercase words and dashes, and the front matter's `name` is the same. The `description` starts with "Use when" and says plainly when Genie Code should use it: that's what it matches on.
- **Placeholders** are filled in per workspace from its configuration (its file over the baseline), in the instructions and every skill: `{PREFIX}`, `{CATALOG}`, `{WAREHOUSE}`, `{WAREHOUSE_DETAILS}`, `{TAGS}`, `{WORKSPACE_TAGS}`, `{PERSONAS}`, `{CLASSIC_POLICIES}` (what each holds: `config/README.md`). Use them instead of writing a name or a limit by hand, so the text stays right when the configuration changes.
- **`<!-- comments -->`** are removed before deploying: use them for notes to the next editor.

## 3. House style

- **Warm, plain and short.** Short sentences, plain words, contractions are fine. Bold the key phrase, not whole sentences. No em dashes.
- **Help, don't block.** Answer what the person asked first, match their level, and offer one next step. A guardrail is mentioned in a sentence and helped with, never a reason to refuse.
- **Say only what's true here.** Check a claim against `config/` before writing it (what the self-service app does, who grants access). Don't name groups, hosts or IDs.
- **Public information only.** Nothing proprietary or internal in these files: they are in the repository, and the instructions reach everyone in every workspace.

## 4. Check, then deploy

1. Read it back in plain words: what Genie Code will now do, and where.
2. In the framework repository only: copy the same change to `terraform/tests/defaults/genie-code/` (the tests check the two match), and run `./scripts/test.sh`.
3. Hand over to the skill **pull-request-from-databricks**. **Every workspace is planned:** each plan comment shows the instructions or the skill's file changing, and nothing else.
