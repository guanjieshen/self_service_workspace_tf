# Future additions (to review)

Ideas that are not built. DESIGN.md describes what exists. Each needs review and a decision before work starts; the configuration is designed so they can be added without changing how workspaces are configured today.

| # | Addition | What it adds | Depends on |
| - | --- | --- | --- |
| F1 | Combined mode | Creating the workspace itself | Network design (VNet, PrivateLink, DNS) |
| F2 | Unity Catalog stream | Catalogs shared between workspaces, storage credentials, external locations | The Unity Catalog team |
| F3 | A request front end | People ask for schemas and folders in a portal or a ticketing system, which runs the jobs | The job contract below |

## Combined mode (F1)

A second stack creates the workspace itself (Premium, VNet injection into an existing VNet, no public IP, front-end and back-end PrivateLink, private DNS) and passes the workspace URL to this stack. `workspace.yaml` would gain a `create: true` option and network settings; the onboarding steps stay the same.

## Unity Catalog stream (F2)

Catalogs shared between workspaces, storage credentials and external locations stay with the Unity Catalog team. This project manages only a workspace's own catalog (`catalog.yaml`) and expects the metastore and the rest to exist.

## A request front end (F3)

Today a workspace admin runs the on-request jobs by hand. A front end (a self-service web app, or a ticketing system such as ServiceNow after an approval) can run them instead, with no change to this repository beyond listing its service principal in `jobs.runners` (`access.yaml`).

### The job contract

What a caller relies on. Changing any of it is a breaking change: say so in `CHANGELOG.md`.

| Job | Find it by tag | Other tags | Parameters |
| --- | --- | --- | --- |
| `<BU> personal schema` | `cd_self_service = personal_schema` | `cd_catalog` (the catalog it creates schemas in), `cd_prefix` (personal schema prefix) | `user` (email), `catalog`, `schema` (empty = personal), `owner_group` (team schema), `reason`, `request_id` |
| `<BU> team folder` | `cd_self_service = team_folder` | `cd_root` (where folders go) | `folder`, `requested_by` (email), `owner_group`, `reason`, `request_id` |

- **Who may run them:** workspace admins and the service principals in `jobs.runners`, with Can manage run. A runner can act for any user (the jobs trust `user` and `requested_by`), so list only callers that authenticate the requester themselves.
- **The job checks every request again:** names, that the group is one of the requester's, and that an existing schema or folder already belongs to the requester. A caller should apply the same rules first, to give a clear message, but does not need to.
- **Results:** each run's output (`dbutils.notebook.exit`) is JSON describing what it created; schemas are also tagged (`cd_managed_by`, `cd_user`, `cd_schema_kind`, `cd_created`, `cd_request_id`), so a caller or an audit can list them in `information_schema.schema_tags`.
- **`request_id`** is free for the caller's own reference (a ticket number); the job keeps it with the run and on the schema.
- **Reading which schemas exist:** runners get `BROWSE` on the workspace catalog (metadata only), so a caller can tell a user they already have a personal schema.

### Requests that need a pull request

Changes to Terraform-managed objects (a team warehouse, a shared schema, extra grants) stay pull requests. A front end that opens them would need: a JSON Schema per configuration file so it can check a file before opening a PR, one file per requested item so concurrent requests do not conflict, and a `request:` block (who asked and why) that Terraform accepts and ignores. None of these exist yet.

### Open questions

| # | Question | Proposed default |
| --- | --- | --- |
| R1 | Who removes the personal schemas of people who left, and after how long? | Out of scope |
| R2 | Which requests need a person to approve them, and who? | Project and team schemas; the BU's platform admins |
| R3 | Should a job refuse a run that has no approved request behind it (a request record the job can read)? | No: the runners are trusted |
