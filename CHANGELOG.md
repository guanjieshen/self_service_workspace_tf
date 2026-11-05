# Changelog

Each release is a tagged version of this repository (`v1.0.0`), with a branch to install from
(`release/v1.0.0`); `VERSION` in your repository says which one you run (or `main @ <commit>`,
copied from `main`). Each entry says what the first plan after an upgrade shows. An upgrade
never touches your `config/` (`install/copy_to_your_repo` keeps it), so each entry also lists,
under **Baseline edits**, the exact YAML to change in `config/defaults/`: new settings to add,
and defaults the release changed that you may want to copy. A setting missing from your baseline
is left alone.

## Unreleased

- The default Genie Code instructions start with **Who you are helping**: many people here are new
  to Databricks, so answer first, match their level, and ask about their role and priorities at
  most once, saving the answer to Genie Code memory. The `onboard-me` skill keeps its profile in
  Genie Code memory instead of a file in the user's folder.

- **An Open your workspace card** (Get started) replaces Genie One Onboarding: it opens Genie One
  in the person's workspace, with the onboarding prompt (now the **guided tour**) the first time
  and plain Genie One after that; **Start the guided tour again** on the card asks it again. The
  app records who had the tour (migration `006_guided_tours.sql`). The Settings section is now
  **Guided tour**; an empty prompt means no tour, not no card. "Ask a question" leaves the
  New here? line (`/ask` still works).
- **The self-service app no longer calls other workspaces** (no cross-workspace access needed).
  Each served workspace's schema job is deployed to the **hub**, and the app talks only to the
  hub; links people open (Genie One, Discover) still go to their own workspace. Terraform binds
  each served workspace's catalog and serverless usage policy to the hub too (the first plan
  shows one workspace binding and the policy's bindings changing). The jobs in the served
  workspaces are no longer deployed: delete them by hand if you had them (Jobs > `<BU>`
  personal schema and team folder).
- **Workspace folders are Coming soon** (a folder is workspace specific): the card is off and the
  folder job is not deployed.
- **A team schema's group is typed, and membership is not checked:** any Entra account group can
  be named (the hub cannot see a person's groups in their workspace).

- **When the app's database does not answer, the app says so:** a person's chosen business unit
  that cannot be read shows "Your business unit can't be read just now. Try again in a minute."
  (503), instead of sending them to choose one they could not save. Forms sent then are not
  sent, and say the same.
- **A Genie Code skill to upgrade, `upgrade-to-a-new-release`:** it finds your version and the
  new one, reads what changed with you, runs the copy (preview, then copy), helps with the
  Baseline edits and guides the pull request. The README now explains the skills, and releases
  and upgrades.

## 1.0.0

The first tagged release: a governed baseline for existing Azure Databricks citizen development
workspaces, configured in YAML and deployed by GitHub Actions, and the self-service app. Set up
from scratch with [docs/SETUP.md](docs/SETUP.md); there is nothing to upgrade from. An
installation copied from `main` before this release upgrades to it like any release.

### Added since the first version of the baseline

- **Genie Code skills for your admins** (`agents/skills/`): `add-workspace`,
  `change-all-workspaces`, `change-one-workspace`, `update-self-service-app` and
  `pull-request-from-databricks`. In your repository's Git folder, Genie Code asks what they want
  in plain language, makes the edit and walks them through the pull request: no git, YAML or
  Terraform needed. Turn them on once per admin (`docs/SETUP.md`, step 2).
- **The self-service app's jobs skip until it is set up:** with `hub.host` empty in
  `config/self-service/hub.yaml` (as it ships), App plan and Deploy the app do nothing, so a first
  install without the app has no failing checks.

- **Every route of both apps has a test request,** and a new one fails the suite until a test
  asks for it (`EveryRoute`).

- **The deploy's own flow is tested** (`scripts/app_deploy.py`, from 44% of its lines to 97%):
  a first install deploys twice, an existing hub once, a plan changes nothing, `app_ids` that
  are not the apps stop it, the database and reader roles, adopting resources, and the hub
  first, then each workspace. The **Database tests** check reports its coverage of the database
  code.

- **Two requests for the same new schema name never share it:** the schema job creates a new
  schema on its own (no `IF NOT EXISTS`), so when two run at once only the first gets it and the
  other stops with "choose another name".
- **The approvals inbox reads each job run once, and side by side** (8 at a time) after a deploy,
  instead of two calls per request one after another.
- **Both apps refuse a form sent from another site** (or another app on the same domain),
  from what the browser says (`Sec-Fetch-Site`): an approval runs a job, and Settings reach
  every page.
- More tests where a mistake would go unnoticed: decisions (a known action, only on requests
  the approver approves), the settings' limits, polling only one's own runs, wrong kinds, and an
  AI summary that fails without blocking the request.
- **Docs match the code, for an organization installing it:**
  - `docs/SETUP.md` has a new step 12, **the self-service app**: what the hub needs (serverless,
    Apps, Lakebase, AI Decide, cross-workspace access behind Private Link), the two-pull-request
    install, and what to do when something goes wrong.
  - No step needs a laptop: the overview, break glass and teardown say which need a terminal.
  - The README describes both parts (the baseline and the app), and its layout lists `apps/`,
    `bundle/` and `config/self-service/`.
  - Classic compute is granted by a platform admin; the docs no longer say the app does it.
  - `AGENTS.md`: `main` is what customers install, and where an environment value may live.
- `config/self-service/app.yaml`: the FAQ links are `null` until you set them (they were
  placeholders).
- **The self-service app's database is tested in CI:** a new **Database tests** check runs its
  migrations, grants and queries against Postgres 17 (they were skipped before). It is not a
  required check, since it needs Docker on the runner.
- **Fixes in the self-service app and its deploy:**
  - The deploy no longer reads a failed CLI call (sign-in, network) as "the database does not
    exist", which could have created it again; only a real not-found counts.
  - The business unit page's return link refuses `/\` paths (an open redirect).
  - A job that cannot start, or a run that does not exist, shows a message instead of an error
    page; recording and start failures are logged.
  - Leftovers of the folder form's owner group are gone.
- **Install and upgrade from a clone, all in Databricks.** Clone this repository (`main`) into a
  Databricks Git folder and run `install/copy_to_your_repo` on serverless (or, in the web
  terminal, `python3 install/copy_to_your_repo.py <source> <target>`): it copies the framework
  without this repository's own environment (the same rules as a release) and stops if any of its
  identifiers would be copied. Run again for an upgrade: your configuration is kept, framework
  files the new version dropped are removed, and new baseline files are listed for you to add.
  The zip and the terminal upgrade steps are gone from `docs/SETUP.md`.

- **Persona request links per business unit.** In the approvals app's Settings (Onboarding), a
  **Business unit** selector (All business units, or one of those the app serves) shows the
  Explorer, Builder and Publisher links to edit. Request workspace access uses the person's own
  business unit's link, or the one for all business units where it has none.
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
  Set it in `config/self-service/app.yaml` (`links.group_request`). Until then the card shows as
  Coming soon.
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
  packages). The Deploy workflow's App plan and Deploy the app jobs deploy it.

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

### The baseline

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
