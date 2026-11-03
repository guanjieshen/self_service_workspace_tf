# Changelog

Each release is a zip named after its version (`v1.0.0`; `VERSION` in the repository says which
one you run). Each entry says what the first plan after an upgrade shows. An upgrade never
touches `config/defaults/` (it is your baseline), so each entry also lists, under **Baseline
edits**, the exact YAML to change there: new settings to add, and defaults the release changed
that you may want to copy. A setting missing from your baseline is left alone.

## Unreleased

- **Choosing a business unit comes first.** Until someone has chosen one (when there are several
  and no lookup function), every page takes them to the choice, then back where they were going;
  they change it later from their name. The choice page is redesigned: one card per business
  unit, with its workspace and catalog. The catalog's "Which business unit are you in?" banner
  is gone.

- **One runner setting for every workflow:** the repository variable `RUNNER` (a JSON `runs-on`
  value) replaces `CHECKS_RUNNER` and `TERRAFORM_RUNNER`. If you set either, set `RUNNER` instead
  and delete them. A pull request from a fork never runs on the runner.

- **Add a group to your workspace** moves to **Build**, next to the folder it lets you share.
- **Genie One Onboarding** says "Opens in Databricks (workspace access is required)", like the Data cards.
- **The folder form no longer asks who can manage the folder.** The requester manages it (and
  the workspace's platform admins), and shares it with others in Databricks once it exists.

- **The AI check runs in the hub** (the apps' own workspace), and so do the approvers' AI
  summaries: AI Decide needs enabling there only, not in every workspace.
- **Validate is simpler:** two questions instead of four. It checks that the name says what it
  holds and that the reason says what it is for and who will use it, and shows a good example
  to copy when either falls short.

- **Sharing groups.** `sharing_groups: [<group>, ...]` in a workspace's file assigns Entra groups
  to the workspace **with every entitlement off**, so people can share folders with them. Their
  members still sign in only through a persona. A plan fails if a sharing group is a persona,
  platform admins or users group, or if the built-in users group has any entitlement. The first
  plan shows no change until a workspace sets the key.
- **The default SQL warehouse is Medium** (was Small). The first plan shows the warehouse's size
  changing in every workspace that doesn't set `sql_warehouse.size` in its own file. Serverless
  warehouses resize without downtime; a Medium warehouse costs about twice a Small one per hour
  it runs.

  **Baseline edits:**

  | File | Change |
  | --- | --- |
  | `config/defaults/access.yaml` | Add `sharing_groups: []` (a top-level key, after `groups:`) |
  | `config/defaults/compute.yaml` | `sql_warehouse.size: Medium` (was `Small`), if you want the new default |

- **A new card, Add a group to your workspace** (Get started): a link to your organization's
  form for adding an Entra group to a workspace with a persona (for example ServiceNow).
  Set it in `config/self-service/app.yaml` (`links.group_request`) or in the approvals app's
  Settings (Onboarding). Until then the card shows as Coming soon.
- Discover data and Review data access requests say **"Opens in Databricks (workspace access is
  required)"**. The onboarding prompt asks about **the data assets you have access to**.
- **Platform admins can manage every requested workspace folder.** The folder job gives the
  workspace's `platform_admins` group CAN_MANAGE, next to the requester and their group, so no
  folder is left without a manager. The group comes from a new field of the Terraform output
  `self_service`, `platform_admins`. The first plan shows only that output changing. Folders
  created before this keep their permissions until they are requested again.

- **Self-service links open in the person's own workspace.** Discover data, Review data access
  requests and Genie One now open in the person's business unit's workspace, not the hub.
  `{host}` and `{workspace_id}` in `config/self-service/app.yaml` links are that workspace's, and
  `o=` is Terraform's workspace ID, so custom URLs work too.
- **Request workspace access says which workspace** it is for.
- **The Genie One Onboarding prompt spells out each step** (Genie One does not start the
  `onboard-me` skill from a link). `{catalog}` in the prompt is the person's workspace catalog.

- **Self-service forms say where a request goes.** A folder request always shows its workspace
  (the person's business unit's), even when there is only one. Schema requests no longer show a
  workspace: Unity Catalog is not tied to one, so they show only the catalog (a choice of catalog
  before someone has chosen a business unit).

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

- **The self-service apps get workspace access in the workspaces they serve**
  (`terraform/self_service.tf`): the baseline gives the users group no entitlements, so without
  it the apps could not use the Jobs API there and found no jobs. The first plan shows two
  entitlements per served workspace.

- **A first install of the self-service app** is two pull requests (the first creates the hub and
  the jobs, the second sets `app_ids`, so Terraform assigns the apps and the deploy grants them
  the jobs), and a deploy says how to clear a Lakebase project that was deleted but not purged.

- **People choose their business unit in the self-service app** while there is no lookup
  function (`bu_lookup`): the catalog asks once (when the app serves more than one business
  unit), the choice is remembered (a new table, migration `005`), shown in the account chip at
  the top right, and changeable from there. Their requests, Genie One Onboarding and Ask a
  question follow it. With a lookup function, it decides and the choice is not offered.

- **The deploy workflow deploys the self-service app** (`deploy.yml`, **App plan** and **Deploy the
  app**): on a pull request, what a deploy would change; after a merge, once the workspaces'
  applies passed, the hub and then each served workspace's jobs. A change to
  `config/self-service/hub.yaml` plans every workspace too (Terraform grants its `app_ids`).

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
