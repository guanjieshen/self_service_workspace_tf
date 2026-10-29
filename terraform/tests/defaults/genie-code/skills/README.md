# Default Genie Code skills

Every workspace gets the skills in this folder, deployed to `/Workspace/.assistant/skills/`, where Genie Code makes them available to every user. Genie Code uses a skill when a request matches its description, or when someone @-mentions it.

- **One folder per skill**, named in lowercase letters, digits and hyphens (for example `build-tagged-assets`).
- **Each folder has a `SKILL.md`** that starts with front matter giving `name` (the folder name) and `description`. Other files in the folder (examples, templates, scripts) are deployed next to it.
- **Markdown files** get the placeholders `{BU}`, `{LOB}`, `{CATALOG}` and `{WAREHOUSE}` filled in, and `<!-- comments -->` removed. Other files are deployed as they are.
- **A workspace can add** its own skills in `config/workspaces/<name>/genie-code/skills/`. They cannot reuse a default skill's name; the plan fails if they do.

Terraform manages only the files it deploys: skills that admins add by hand in the workspace are left alone, but edits to a managed skill are replaced on the next apply. This README is not deployed.
