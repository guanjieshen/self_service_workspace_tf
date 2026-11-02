# Changelog

Each release is a zip named after its version (`v1.0.0`; `VERSION` in the repository says which
one you run). Each entry says what the first plan after an upgrade shows. An upgrade never
touches `config/defaults/` (it is your baseline), so each entry also lists, under **Baseline
edits**, the exact YAML to change there: new settings to add, and defaults the release changed
that you may want to copy. A setting missing from your baseline is left alone.

## Unreleased

- **The plan guard no longer blocks.** It still lists hard-to-undo, security-weakening and
  access-removing changes under **Before merging** in the plan comment, but no check fails and no
  label is needed: the `allow-risky-changes` label and its checks on plan and apply are gone.
  Code owner review (and `apply_approvers`, if set) is the approval. You can delete the label.
- `tf.sh`: the plan guard now runs on macOS's bash too (an empty argument list skipped it there).

- **Setup needs no terminal.** SETUP.md steps 3 to 5 are done in the Azure portal and the GitHub web
  UI; `scripts/setup.py` stays as an optional shortcut. A new workflow, **Show the sign-in subject**
  (Actions > Run workflow), prints the two subjects for the federated credentials, which include
  numeric IDs the web pages do not show.
- A new default Genie Code skill, **`onboard-me`** (`config/defaults/genie-code/skills/onboard-me/`): the
  first time someone says "onboard me", it introduces the workspace, lists the data they can see,
  suggests three first questions and asks what they want to achieve; later sessions coach them.
  It keeps a short profile in the user's own folder (`.onboarding/profile.md`), only with their
  permission. The first plan adds the skill's file to every workspace.

- **The self-service app moved into this repository** (`apps/self-service/`, from the archived
  `self_service_app` repository at `final-before-merge`), deployed by Databricks Asset Bundles,
  not Terraform:
  - `bundle/hub/` (both apps and their Lakebase database, in the hub: `config/self-service/hub.yaml`);
  - `bundle/jobs/` (the two jobs, in every workspace without `self_service: false`);
  - `scripts/app_build.py` and `scripts/app_deploy.py` build and deploy them from
    `config/self-service/app.yaml`, the workspace files and each workspace's Terraform output
    `self_service`. Hub first, then the jobs.

  The app's tests are a new suite, `scripts/test.sh app` (the Tests check installs the app's
  packages). Nothing deploys the app from GitHub Actions yet.

- **The self-service app's needs in the workspaces it serves** (`terraform/self_service.tf`), ahead
  of the app moving into this repository. Nothing changes until `app_ids` in
  `config/self-service/hub.yaml` are set:
  - the apps' two service principals are assigned to each workspace and may see its catalog
    (`USE_CATALOG`, `BROWSE`);
  - the pipeline's identity, which runs the self-service jobs, may use the workspace's serverless
    usage policy;
  - a new output, `self_service`, gives the app's deploy the workspace's prefix, ID, host,
    catalog and usage policy.

  A workspace opts out with `self_service: false` in its file (a new workspace key; the hub
  itself, for example). The first plan after the upgrade shows the pipeline added to the usage
  policy's users.

## 1.0.0

The first release: a governed baseline for existing Azure Databricks citizen development
workspaces, configured in YAML and deployed by GitHub Actions. Set up from scratch with
[docs/SETUP.md](docs/SETUP.md); there is nothing to upgrade from.

**What every workspace gets** (`config/defaults/`):

| Area | What |
| --- | --- |
| Access | Personas from Entra ID groups: users (Databricks One), explorers (SQL), builders and publishers (workspace); `{prefix}_platform_admins` are the only workspace admins; the built-in `users` group gets no entitlements |
| Compute | A serverless default SQL warehouse; the Serverless Starter Warehouse for platform admins only; classic cluster policies for interactive, job and pipeline clusters (one cluster per user each, granted by the self-service app) |
| Cost | One serverless usage policy per workspace, `{PREFIX}-0-SELF-SERVICE`, and one list of chargeback tags on serverless usage, the warehouse and classic clusters |
| Catalog | One catalog per workspace, `{prefix}_citizen_dev`: bound to the workspace, owned by the pipeline, all privileges and `MANAGE` for the platform admins, `USE` for personas, predictive optimization on; the workspace's default catalog |
| Settings | Legacy access, DBFS root and mounts disabled; user isolation; tokens for admins only, 90 days; the DBFS file browser off (downloads and exports allowed, one setting each); Git limited to github.com; Unity Gateway enforced; Microsoft Teams only; SQL statement timeout; a label where a workspace sets one |
| Genie Code | Workspace instructions (work in your personal schema, use the default warehouse, keep the chargeback tags) and skills |

**How changes are made:** a pull request plans each workspace it concerns and posts the plan
with an AI impact review. A plan guard lists changes that are hard to undo, weaken security or
take access away, for the reviewer. Merging applies; a weekly drift check opens an issue when a workspace no longer
matches; deleting a workspace's file retires it. A setting set to `null` is left alone,
never reset.

**Done by hand** (no API yet): data classification and data quality monitoring on the
catalog, and the workspace theme and Genie One look (SETUP.md, step 9).
