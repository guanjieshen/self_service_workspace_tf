# Future additions (to review)

Ideas that are not built. DESIGN.md describes what exists. Each needs review and a decision before work starts; the configuration is designed so they can be added without changing how workspaces are configured today.

| # | Addition | What it adds | Depends on |
| - | --- | --- | --- |
| F1 | Combined mode | Creating the workspace itself | Network design (VNet, PrivateLink, DNS) |
| F2 | Unity Catalog stream | Catalogs shared between workspaces, storage credentials, external locations | The Unity Catalog team |
| F3 | The self-service app | Schemas and workspace folders on request | Its own repository; the catalog this repository creates |

## Combined mode (F1)

A second stack creates the workspace itself (Premium, VNet injection into an existing VNet, no public IP, front-end and back-end PrivateLink, private DNS) and passes the workspace URL to this stack. `workspace.yaml` would gain a `create: true` option and network settings; the onboarding steps stay the same.

## Unity Catalog stream (F2)

Catalogs shared between workspaces, storage credentials and external locations stay with the Unity Catalog team. This project manages only a workspace's own catalog (`catalog.yaml`) and expects the metastore and the rest to exist.

## The self-service app (F3)

Schemas and workspace folders are requested through the self-service app, which lives in its own repository and deploys its own jobs. What it relies on here:

- **The workspace catalog** (`{bu}_citizen_dev`), owned by the platform admins group. Personas have only `USE CATALOG` and `USE SCHEMA` on it; the app grants on the schemas it creates.
- **Catalog grants are authoritative:** a privilege granted on the catalog outside `catalog.yaml` is removed on the next apply. The app's service principal needs a privilege on the catalog (for example `CREATE SCHEMA`): add it to `catalog.yaml`, not by hand.
- **The persona groups** each workspace names in its `access.yaml`.
