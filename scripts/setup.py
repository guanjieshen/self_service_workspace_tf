#!/usr/bin/env python3
"""One-time setup, one step per team. Each step prints a bash script; --run runs it.

    scripts/setup.py state      --subscription <id> --resource-group <rg> --location <region>
                                --storage-account <name> [--container tfstate]          (cloud team)
    scripts/setup.py identity   --subscription <id> --resource-group <rg> --storage-account <name>
                                --repo <org>/<repo> [--name sp-citizen-dev-terraform]
                                [--container tfstate]                                    (Entra admin)
    scripts/setup.py github     --repo <org>/<repo> --client-id <app id> --tenant-id <id>
                                --subscription <id> [--approvers <org>/<team>]          (GitHub admin)
    scripts/setup.py databricks --client-id <app id> [--account-profile <profile>]
                                [--name sp-citizen-dev-terraform] [<workspace> ...]      (Databricks account admin)

Without --run, nothing happens: the script is printed, to read first or to send to the team
that owns the step. With --run it runs here (bash, stopping at the first error). Every step
checks before it creates, so running one again is safe. docs/RUNBOOK.md says who runs which
step and in what order.

  state       the storage account and container for Terraform state (no public access, no
              shared keys, versioning and soft delete), and config/backend.hcl
  identity    the Entra app and service principal CI signs in as, its two GitHub federated
              credentials (pull requests; the main branch) and its role on the state container
  github      repository variables, the labels, the apply-approval environment (main only;
              --approvers adds required reviewers) and branch protection on main
  databricks  adds the service principal to the Databricks account and makes it workspace admin
              of each workspace given (default: every folder in config/workspaces/)
"""
import argparse
import json
import pathlib
import re
import shlex
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import workspaces as wsf  # noqa: E402

ROOT = wsf.ROOT
ISSUER = "https://token.actions.githubusercontent.com"
# The checks branch protection requires: the Plan workflow's jobs that run on every pull request.
REQUIRED_CHECKS = ["Format and validate", "Tests"]
q = shlex.quote


def state(a):
    backend = (f'# Shared Terraform state in Azure Storage (Entra sign-in only; shared keys are disabled).\n'
               f'# scripts/tf.sh adds key=citizen-dev/<workspace>.tfstate for each workspace.\n'
               f'resource_group_name  = "{a.resource_group}"\n'
               f'storage_account_name = "{a.storage_account}"\n'
               f'container_name       = "{a.container}"\n'
               f'use_azuread_auth     = true\n')
    rg, sa = q(a.resource_group), q(a.storage_account)
    return f"""# Terraform state storage: one container, one state file per workspace.
az account set --subscription {q(a.subscription)}
az group show -n {rg} >/dev/null 2>&1 || az group create -n {rg} -l {q(a.location)} -o none
az storage account show -n {sa} -g {rg} >/dev/null 2>&1 ||
  az storage account create -n {sa} -g {rg} -l {q(a.location)} --sku Standard_ZRS --kind StorageV2 \\
    --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false -o none
# Keep earlier versions of each state file, and deleted ones for 30 days.
az storage account blob-service-properties update -n {sa} -g {rg} --enable-versioning true \\
  --enable-delete-retention true --delete-retention-days 30 -o none
az storage container-rm show -n {q(a.container)} --storage-account {sa} -g {rg} >/dev/null 2>&1 ||
  az storage container-rm create -n {q(a.container)} --storage-account {sa} -g {rg} --public-access off -o none
# config/backend.hcl tells Terraform where the state is. In the repository it is written;
# anywhere else it is printed, to send to the platform team.
if [ -d config/defaults ]; then
  cat > config/backend.hcl <<'EOF'
{backend}EOF
  echo "State storage ready; wrote config/backend.hcl (commit it: it holds no secrets)."
else
  echo "State storage ready. Send this to the platform team, for config/backend.hcl:"
  cat <<'EOF'
{backend}EOF
fi
"""


def identity(a):
    name, repo = q(a.name), a.repo
    creds = [("github-pull-requests", "pull_request", "Plan workflow: every pull request"),
             ("github-main", "ref:refs/heads/main", "Apply and Drift workflows: the main branch")]
    lines = [f"""# The identity GitHub Actions signs in as (no secret: GitHub OIDC federated credentials).
az account set --subscription {q(a.subscription)}
APP_ID=$(az ad app list --display-name {name} --query "[0].appId" -o tsv)
[ -n "$APP_ID" ] || APP_ID=$(az ad app create --display-name {name} --sign-in-audience AzureADMyOrg --query appId -o tsv)
SP_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)
[ -n "$SP_ID" ] || SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
# The repository's subject prefix: repositories created since July 2026 include numeric IDs.
PREFIX=$(gh api repos/{repo}/actions/oidc/customization/sub --jq .sub_claim_prefix)
[ -n "$PREFIX" ] || {{ echo "Could not read the OIDC subject prefix of {repo} (gh auth login?)"; exit 1; }}"""]
    for cred, subject, what in creds:
        body = ('{"name": "%s", "issuer": "%s", "subject": "\'"$PREFIX"\':%s", "description": "%s", '
                '"audiences": ["api://AzureADTokenExchange"]}') % (cred, ISSUER, subject, what)
        lines.append(f"""[ "$(az ad app federated-credential list --id "$APP_ID" --query "[?name=='{cred}'] | length(@)" -o tsv)" != 0 ] ||
  az ad app federated-credential create --id "$APP_ID" --parameters '{body}' -o none""")
    lines.append(f"""# Read and write state, in the state container only.
SCOPE="$(az storage account show -n {q(a.storage_account)} -g {q(a.resource_group)} --query id -o tsv)/blobServices/default/containers/{a.container}"
[ "$(az role assignment list --assignee "$SP_ID" --scope "$SCOPE" --role "Storage Blob Data Contributor" --query "length(@)" -o tsv)" != 0 ] ||
  az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \\
    --role "Storage Blob Data Contributor" --scope "$SCOPE" -o none
echo "Service principal ready. For the next steps:"
echo "  client ID (AZURE_CLIENT_ID): $APP_ID"
echo "  tenant ID (AZURE_TENANT_ID): $(az account show --query tenantId -o tsv)"
echo "  subscription (AZURE_SUBSCRIPTION_ID): $(az account show --query id -o tsv)"
""")
    return "\n".join(lines)


def github(a):
    repo = q(a.repo)
    env = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
    reviewers = ""
    if a.approvers:
        org, team = a.approvers.split("/", 1)
        reviewers = f'TEAM_ID=$(gh api orgs/{q(org)}/teams/{q(team)} --jq .id)\n'
        env["reviewers"] = [{"type": "Team", "id": "__TEAM_ID__"}]
    env_json = json.dumps(env).replace('"__TEAM_ID__"', "$TEAM_ID")
    # Without --approvers, only create it: a PUT would drop reviewers added since in the UI.
    put_env = "" if a.approvers else f"gh api repos/{a.repo}/environments/apply-approval >/dev/null 2>&1 ||\n  "
    protection = json.dumps({
        "required_status_checks": {"strict": False, "contexts": REQUIRED_CHECKS},
        "enforce_admins": False,
        "required_pull_request_reviews": {"require_code_owner_reviews": True, "required_approving_review_count": 1},
        "restrictions": None,
    })
    return f"""# Repository settings for the Plan, Apply and Drift workflows (docs/github-actions.md).
gh variable set AZURE_CLIENT_ID -R {repo} -b {q(a.client_id)}
gh variable set AZURE_TENANT_ID -R {repo} -b {q(a.tenant_id)}
gh variable set AZURE_SUBSCRIPTION_ID -R {repo} -b {q(a.subscription)}
gh label create allow-risky-changes -R {repo} --force --color B60205 \\
  --description "A person reviewed the plan's hard-to-undo or security-weakening changes"
gh label create drift -R {repo} --force --color FBCA04 --description "A workspace no longer matches its configuration"
# The approval step before each apply: main only{', and these reviewers' if a.approvers else '; add required reviewers to make applies wait for one'}.
{reviewers}{put_env}gh api -X PUT repos/{a.repo}/environments/apply-approval --input - >/dev/null <<EOF
{env_json}
EOF
gh api repos/{a.repo}/environments/apply-approval/deployment-branch-policies --jq '.branch_policies[].name' | grep -qx main ||
  gh api -X POST repos/{a.repo}/environments/apply-approval/deployment-branch-policies -f name=main -f type=branch >/dev/null
# main: pull requests only, the checks pass, and code owners approve (.github/CODEOWNERS).
gh api -X PUT repos/{a.repo}/branches/main/protection --input - >/dev/null <<'EOF'
{protection}
EOF
echo "Repository {a.repo} is set up."
"""


def databricks(a):
    hosts = []
    folders = a.workspaces or [d.name for d in sorted(wsf.WORKSPACES.glob("*")) if (d / "workspace.yaml").exists() and not d.name.startswith("_")]
    for w in folders:
        info = wsf.workspace_info(wsf.ws_dir(w))
        if not info["id"]:
            raise SystemExit(f"{w}: no workspace ID (an adb-<id> host, or id: in workspace.yaml)")
        hosts.append((w, info["id"]))
    profile = f" -p {q(a.account_profile)}" if a.account_profile else ""
    lines = [f"""# The service principal in the Databricks account, and workspace admin where Terraform runs.
# Needs a Databricks account admin.{'' if a.account_profile else ' Sign in first: databricks auth login --host https://accounts.azuredatabricks.net --account-id <id>'}
DBX_SP=$(databricks account service-principals list{profile} --filter 'applicationId eq "{a.client_id}"' -o json |
  python3 -c 'import json, sys; r = json.load(sys.stdin); print(r[0]["id"] if r else "")')
[ -n "$DBX_SP" ] || DBX_SP=$(databricks account service-principals create{profile} --application-id {q(a.client_id)} \\
  --display-name {q(a.name)} -o json | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')"""]
    for w, wid in hosts:
        lines.append(f"""databricks account workspace-assignment update{profile} {wid} "$DBX_SP" --json '{{"permissions": ["ADMIN"]}}' >/dev/null
echo "{w}: the service principal is workspace admin."
""")
    lines.append("""echo "Still to do by hand, once: in the account console, give the service principal the permission to"
echo "create budget policies (serverless usage policies), or set budget_policies.enabled: false in cost.yaml."
""")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(prog="setup.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="step", required=True)
    p = sub.add_parser("state")
    for f in ("--subscription", "--resource-group", "--location", "--storage-account"):
        p.add_argument(f, required=True)
    p.add_argument("--container", default="tfstate")
    p = sub.add_parser("identity")
    for f in ("--subscription", "--resource-group", "--storage-account", "--repo"):
        p.add_argument(f, required=True)
    p.add_argument("--container", default="tfstate")
    p.add_argument("--name", default="sp-citizen-dev-terraform")
    p = sub.add_parser("github")
    for f in ("--repo", "--client-id", "--tenant-id", "--subscription"):
        p.add_argument(f, required=True)
    p.add_argument("--approvers", help="<org>/<team> required to approve each apply")
    p = sub.add_parser("databricks")
    p.add_argument("--client-id", required=True)
    p.add_argument("--account-profile")
    p.add_argument("--name", default="sp-citizen-dev-terraform")
    p.add_argument("workspaces", nargs="*", help="workspace folders (default: all in config/workspaces/)")
    for s in sub.choices.values():
        s.add_argument("--run", action="store_true", help="run the script here instead of printing it")
    a = ap.parse_args(argv)

    for value in (getattr(a, "repo", None),):
        if value is not None and not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
            raise SystemExit(f"--repo must be <org>/<repo>, not {value!r}")
    if getattr(a, "approvers", None) and not re.fullmatch(r"[\w.-]+/[\w.-]+", a.approvers):
        raise SystemExit(f"--approvers must be <org>/<team>, not {a.approvers!r}")
    script = {"state": state, "identity": identity, "github": github, "databricks": databricks}[a.step](a)
    if not a.run:
        print("#!/usr/bin/env bash\nset -euo pipefail\n" + script)
        return 0
    return subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
