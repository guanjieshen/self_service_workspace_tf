---
name: upgrade-to-a-new-release
description: Use when someone wants to update their repository to a newer version of this framework (a new release, or the latest from the framework's main), asks "is there a new version", "how do I get the latest changes", or "upgrade". Finds their version and the new one, shows what changed, runs install/copy_to_your_repo in preview then copy (their configuration is kept), helps with the Baseline edits, and hands over to pull-request-from-databricks.
---

# Upgrade to a new release

The person may not know git. Do one step at a time, in plain words, and wait for them. Never edit framework files by hand to "upgrade": the copy does it, and keeps their configuration.

There are **two Git folders**:

- **The framework:** a clone of the framework's repository (the one they installed from). It is only a source: nothing is committed there.
- **Theirs:** their organization's repository, where every change is a pull request.

## 1. Which version they run, and which is new

1. In **their** Git folder, open `VERSION` at the top: `v1.0.0` (a release), or `main @ <commit>` or `main` (copied from the framework's `main`).
2. In the **framework** Git folder, see the versions: the branch menu lists `release/<version>` branches (for example `release/v1.1.0`); **Pull** first so the list is current.
3. Agree which to upgrade to: the newest `release/<version>` is the usual choice. `main` is the newest unreleased work; use it only if they were asked to.

## 2. What changed

In the framework's `CHANGELOG.md` (on the new version's branch), read with them every section **newer than their `VERSION`**, newest first, in plain words: what each change does for their workspaces and people. Note each **Baseline edits** table: those are the changes to make by hand in their `config/defaults/` (step 5), because an upgrade never changes their configuration.

If their `VERSION` is `main` (no commit), they cannot tell exactly where they were: read every section since the last release before the one they upgrade to, and say so.

## 3. Get the new version, and a branch for it

1. **Framework** Git folder: switch to the new version's branch (`release/<version>`), or **Pull** on `main`.
2. **Their** Git folder: switch to `main` and **Pull**, then **Create branch**, for example `upgrade-v1.1.0`.

## 4. Copy: preview, then copy

1. In the **framework** Git folder, open `install/copy_to_your_repo` (a notebook).
2. Set `source` to the framework's Git folder path and `target` to theirs (each folder's menu > **Copy path**; both start with `/Workspace/`), and `mode` to `preview`. **Run all** on serverless.
3. Read the output with them. Because their repository has `VERSION`, it is an upgrade:
   - **replace:** framework files with the new version's;
   - **remove:** framework files the new version no longer has (only in the framework's own folders; never their own workflows);
   - **yours:** their configuration, kept as it is: `config/defaults/`, their workspace files, `config/setup.yaml`, `config/self-service/`, `.github/CODEOWNERS`;
   - **baseline:** new files in `config/defaults/`, not copied: add them yourself only if they want those settings (step 5);
   - **keep:** their own files; **skip:** the framework repository's own environment, never copied.

   If it stops with "This repository's own identifiers would be copied", nothing was written: tell the framework's maintainers.
4. If it reads right: set `mode` to `copy` and **Run all** again. `VERSION` now says the new version.

In the Databricks web terminal the same is one command: `python3 install/copy_to_your_repo.py <framework folder> <their folder>` to preview, with `--copy` to write.

## 5. The Baseline edits

For each **Baseline edits** row from step 2, ask whether they want it (a new setting, or a default the release changed). For each yes, make the edit in `config/defaults/` (the skill **change-all-workspaces** knows how). A setting they leave out stays "left alone", so nothing turns on by itself.

## 6. Review and deploy

Hand over to the skill **pull-request-from-databricks**. On the pull request:

- **Every workspace is planned** (the framework's Terraform changed). Go through the plan comments with them: they should show only what the changelog said.
- If the self-service app is set up, **App plan** shows what its deploy changes.
- A check that was green before and is red now: read its message; if it points at framework code, tell the framework's maintainers rather than editing it.

After the merge, the new version is deployed. Delete the upgrade branch, and in their Git folder switch back to `main` and **Pull**.
