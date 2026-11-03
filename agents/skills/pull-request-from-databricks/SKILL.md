---
name: pull-request-from-databricks
description: Use when someone has changed files in this repository's Databricks Git folder (or another skill finished an edit) and needs to get the change reviewed and deployed: make a branch, commit and push, open a pull request on GitHub, read the plan comment, and merge. Also use when they ask how to "save", "publish", "deploy" or "submit" a change, or why a check failed.
---

# Get a change reviewed and deployed

The person may never have used git. Explain each step in one plain sentence, do one step at a time, and wait for them to say it is done. Never run git commands yourself, and never deploy anything: **a change reaches a workspace only when its pull request is merged** (GitHub Actions deploys it).

## The words, in plain language

- **Branch:** a private copy of the files where the change waits for review. `main` is what is deployed.
- **Commit and push:** save the change to the branch on GitHub.
- **Pull request:** asks for the change to be reviewed and merged into `main`.
- **Plan comment:** GitHub Actions writes, on the pull request, what the change will do in each workspace before anything happens.

## Steps

1. **A branch first.** In the Git folder (the folder's name at the top of the file browser), click the branch name, then **Create branch**. Name it after the change, lowercase with dashes, for example `add-finance-workspace`. If they already have changes on `main`, that is fine: creating the branch carries them over.
2. **Look at the change together.** In the Git folder dialog, the **Changes** list shows each file. Read the diff with them in plain words ("this sets the warehouse to Medium in the hr workspace"). Remove anything they did not mean to change.
3. **Commit and push.** In the same dialog: a short message saying what and why (for example `Add the finance workspace`), then **Commit & push**.
4. **Open the pull request.** On GitHub, open the repository; a yellow bar offers **Compare & pull request** for the new branch. Otherwise: **Pull requests > New pull request**, base `main`, compare the branch. Title: what changes. Description: why. **Create pull request.**
5. **Wait for the checks** (a few minutes). On the pull request:
   - **Format and validate** and **Tests** must be green.
   - **Plan <workspace>** for each workspace the change concerns, with a comment titled **Plan: `<workspace>`**.
6. **Read the plan comment with them.** It starts with a risk summary and a table of what changes. Under **Before merging** it lists anything hard to undo or that weakens security or removes access: say what each one means, and that a person decides whether that is intended. Nothing is applied yet.
7. **Review and merge.** A code owner approves (`.github/CODEOWNERS` says who). Then **Merge pull request**. GitHub Actions applies it: **Actions** tab, the **Deploy** run; it may wait for an approval in the `apply-approval` environment.
8. **Clean up:** delete the branch (GitHub offers it after the merge), and in the Git folder switch back to `main` and **Pull**.

## When something is red

- **Format and validate failed:** open the failed check; the error names the file and the key. The usual causes: a YAML indentation slip (two spaces per level, no tabs), a misspelled key, or a value of the wrong kind. Fix it in the Git folder, commit and push again: the checks run again by themselves.
- **A plan failed:** the plan comment says why at the top, often something outside the repository (a group not in the account, the pipeline's identity not an admin in the workspace). Those are fixed outside GitHub; then re-run the check (**Re-run jobs**).
- **Tests failed:** a framework file was changed. Organizations change only `config/` and `.github/CODEOWNERS`; undo the other change.

## Never

- Never commit to `main` directly or merge without a reviewed plan.
- Never paste a password, token or secret into a file or a comment.
