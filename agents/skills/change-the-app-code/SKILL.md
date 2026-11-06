---
name: change-the-app-code
description: Use when the change is to the framework's own code rather than a setting: a new or changed card, form, page or wording in the Citizen Development app or the admin app, a job's behaviour, the build or deploy scripts, the Terraform, a test. Reads AGENTS.md and the guide for that part first, makes the change with its tests, updates the guides in agents/ and CHANGELOG.md so the next person (or Genie Code) knows, then the pull request. Not for an organization's own settings (those are other skills).
---

# Change the framework's code

**First, is this a setting?** Most requests are a setting, not code: the banner, links, branding, the AI model, who approves, a workspace's groups. Those are the skills **update-self-service-app**, **change-one-workspace** and **change-all-workspaces**. In an organization's own repository, framework code (anything outside `config/` and `.github/CODEOWNERS`) is replaced on the next upgrade: a fix there goes to the framework's maintainers. Say so and stop, unless this is the framework's repository.

## 1. Read before you change

1. **`AGENTS.md`**: the workflow, the rules, and the table **What to change with what**.
2. **The guide for the part**: `agents/app.md` (the apps, the jobs), `agents/design.md` (anything people read or see), `agents/database.md` (what the apps store: the skill **change-the-database**), `agents/terraform.md`, `agents/config.md`.
3. The code around the change: match its style, its naming and how much it comments.

## 2. Say the plan, get a yes

In plain words: what changes for the people who use it, which files, which tests, and anything risky (data, access, every workspace). Keep it simple: prefer a fixed, sensible behaviour to a new option.

## 3. Make it, with its tests

Change the code and **its tests together** (every change ships with tests; a new page needs a test request, `tests/test_ui.py`, EveryRoute). Run `./scripts/test.sh` (or the part: `app`, `python`, `terraform`) and fix what fails. For anything people see, look at it in a local preview (`agents/app.md`, "Run and test") and show the person.

## 4. Keep the guides and the changelog true (AGENTS.md)

Before the pull request, in the same change:
- **`CHANGELOG.md`** under **Unreleased**: what changed for the people who use it, and what the first plan or deploy after it shows. The pull request check **Changelog for framework changes** fails without it.
- **The guide** that describes what you changed (the check names it): fix anything it says that is no longer true, and add any rule or gotcha you learned.
- **The skill** that guides what an admin does, if that changed (and `config/README.md` for a key).
- **A new skill:** the tables in `README.md` and `docs/SETUP.md` (step 2).

## 5. The pull request

The skill **pull-request-from-databricks**. In the description: what, why, the tests, and what you tried by hand.

## Never

- Never skip or weaken a test to make a change pass; never change a workspace, a job or the database by hand; never paste a secret.
