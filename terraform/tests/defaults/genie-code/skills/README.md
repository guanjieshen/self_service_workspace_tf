# Default Genie Code skills

Every workspace gets the skills in this folder, deployed to `/Workspace/.assistant/skills/`, where Genie Code makes them available to every user. Genie Code uses a skill when a request matches its description, or when someone @-mentions it.

- **One folder per skill**, named in lowercase letters, digits and hyphens (for example `build-tagged-assets`).
- **Each folder has a `SKILL.md`** that starts with front matter giving `name` (the folder name) and `description`. Other files in the folder (examples, templates, scripts) are deployed next to it.
- **Markdown files** get the placeholders `{PREFIX}`, `{CATALOG}`, `{WAREHOUSE}`, `{TAGS}` and `{WORKSPACE_TAGS}` filled in, and `<!-- comments -->` removed. Other files are deployed as they are.
- **Every workspace gets these skills**, plus its own: `config/workspaces/<name>/genie-code/skills/`, laid out the same way. A workspace skill with the same folder name replaces the baseline's, in that workspace ([config/README.md](../../../README.md#genie-code-for-one-workspace)).

Terraform manages only the files it deploys: skills that admins add by hand in the workspace are left alone, but edits to a managed skill are replaced on the next apply. This README is not deployed.

## Adding or changing a skill

Follow `agents/skills/change-genie-code/SKILL.md` (or ask Genie Code to, in a Git folder of this repository): where each kind of change goes, the placeholders, the house style, and the pull request. Start a new skill from its template, `agents/skills/change-genie-code/template-SKILL.md`.
