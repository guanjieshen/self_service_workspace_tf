#!/usr/bin/env python3
"""One-time setup, one step per team. Each step prints a bash script; --run runs it.

    scripts/setup.py state        the cloud team
    scripts/setup.py identity     an Entra admin
    scripts/setup.py github       a GitHub admin

Every value comes from config/setup.yaml: the required values at the top, three optional ones
with defaults below (docs/SETUP.md, step 1). A flag overrides one value for one run (for
example --storage-account x). `identity --run` writes the client ID it creates into the
file, for the steps after it. The Azure steps stop unless the Azure CLI is signed in to tenant_id. In the
framework's own repository, dev/setup.yaml is read instead when it exists, so a release keeps
a blank config/setup.yaml.

Without --run, nothing happens: the script is printed, to read first or to send to the team
that owns the step. With --run it runs here (bash, stopping at the first error). Every step
checks before it creates, so running one again is safe. docs/SETUP.md says who runs which
step and in what order.

  state       the storage account and container for Terraform state (no public access, no
              shared keys, versioning and soft delete), and config/backend.hcl
  identity    the Entra app and service principal CI signs in as, its two GitHub federated
              credentials (pull requests; the main branch) and its role on the state container
  github      repository variables, the labels, the apply-approval environment (main only;
              apply_approvers adds required reviewers) and branch protection on main

The Databricks account step (the service principal in the account, workspace admin, the budget
policy permission) is done by hand: docs/SETUP.md, step 6.
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
# The checks branch protection requires: the Checks workflow's jobs, on every pull request.
REQUIRED_CHECKS = ["Format and validate", "Tests"]
q = shlex.quote


def signed_in(a):
    """Select the subscription, and stop unless the Azure CLI is signed in to the right tenant."""
    return f"""az account set --subscription {q(a.subscription)}
[ "$(az account show --query tenantId -o tsv)" = {q(a.tenant_id)} ] ||
  {{ echo "The Azure CLI is signed in to another tenant: az login --tenant {a.tenant_id}"; exit 1; }}"""


def state(a):
    backend = (f'# Shared Terraform state in Azure Storage (Entra sign-in only; shared keys are disabled).\n'
               f'# scripts/tf.sh adds key=citizen-dev/<workspace>.tfstate for each workspace.\n'
               f'resource_group_name  = "{a.resource_group}"\n'
               f'storage_account_name = "{a.storage_account}"\n'
               f'container_name       = "{a.container}"\n'
               f'use_azuread_auth     = true\n')
    rg, sa = q(a.resource_group), q(a.storage_account)
    return f"""# Terraform state storage: one container, one state file per workspace.
{signed_in(a)}
LOCATION={q(a.location)}
az group show -n {rg} >/dev/null 2>&1 || az group create -n {rg} -l "$LOCATION" -o none
if az storage account show -n {sa} -g {rg} >/dev/null 2>&1; then
  # Someone else's account: use it as it is (only the container below is added).
  echo "Using the existing storage account {a.storage_account}; its settings are left as they are."
else
  az storage account create -n {sa} -g {rg} -l "$LOCATION" --sku Standard_ZRS --kind StorageV2 \\
    --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false -o none
  # Keep earlier versions of each state file, and deleted ones for 30 days.
  az storage account blob-service-properties update -n {sa} -g {rg} --enable-versioning true \\
    --enable-delete-retention true --delete-retention-days 30 -o none
fi
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
    creds = [("github-pull-requests", "pull_request", "Plans: every pull request"),
             ("github-main", "ref:refs/heads/main", "Applies and drift checks: the main branch")]
    lines = [f"""# The identity GitHub Actions signs in as (no secret: GitHub OIDC federated credentials).
echo "Repository: {repo} (from {a.repo_source}). Entra will trust only its pull requests and main branch."
{signed_in(a)}
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
echo "Step 6 (by hand, a Databricks account admin): add it to the Databricks account with this"
echo "application ID, make it workspace admin, and let it create budget policies (docs/SETUP.md)."
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
    # Without apply_approvers, only create it: a PUT would drop reviewers added since in the UI.
    put_env = "" if a.approvers else f"gh api repos/{a.repo}/environments/apply-approval >/dev/null 2>&1 ||\n  "
    protection = json.dumps({
        "required_status_checks": {"strict": False, "contexts": REQUIRED_CHECKS},
        "enforce_admins": False,
        "required_pull_request_reviews": {"require_code_owner_reviews": True, "required_approving_review_count": 1},
        "restrictions": None,
    })
    return f"""# Repository settings for the workflows (docs/github-actions.md).
echo "Repository: {a.repo} (from {a.repo_source})."
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


# Each value: (flag, key in config/setup.yaml, default, the steps it is required for).
OPTIONS = [
    ("--tenant-id", "tenant_id", None, {"state", "identity", "github"}),
    ("--subscription", "subscription_id", None, {"state", "identity", "github"}),
    ("--location", "state_location", None, {"state"}),
    ("--resource-group", "state_resource_group", None, {"state", "identity"}),
    ("--storage-account", "state_storage_account", None, {"state", "identity"}),
    ("--container", "state_container", None, {"state", "identity"}),
    ("--repo", "github_repo", None, set()),          # default: this clone's GitHub origin
    ("--name", "pipeline_name", "sp-citizen-dev-terraform", set()),
    ("--approvers", "apply_approvers", None, set()),
    ("--client-id", "pipeline_client_id", None, {"github"}),   # written by identity
]
WRITTEN_BY_IDENTITY = {"pipeline_client_id"}
STEPS = {"state": state, "identity": identity, "github": github}


def shown(path):
    """The path as people see it: relative to the repository when it is inside it."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def origin_repo():
    """<org>/<repo> of this clone's GitHub origin, or None."""
    url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else None


def setup_file():
    dev = ROOT / "dev/setup.yaml"
    return dev if dev.exists() else ROOT / "config/setup.yaml"


def remember(path, key, value):
    """Write value into the setup file's key, if it is still null."""
    lines = path.read_text().split("\n")
    for n, line in enumerate(lines):
        if re.match(rf"^{key}:\s*null\b", line):
            lines[n] = re.sub(r"null", value, line, count=1)
            path.write_text("\n".join(lines))
            return True
    return False


def run(script, path):
    """Run the script, showing its output, and keep the IDs `identity` prints in the setup file."""
    proc = subprocess.Popen(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    for line in proc.stdout:
        print(line, end="", flush=True)
        for label, key in (("AZURE_CLIENT_ID", "pipeline_client_id"),):
            m = re.search(rf"\({label}\): (\S+)", line)
            if m and remember(path, key, m.group(1)):
                print(f"  (saved as {key} in {shown(path)})")
    return proc.wait()


def main(argv):
    ap = argparse.ArgumentParser(prog="setup.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="step", required=True)
    for step in STEPS:
        p = sub.add_parser(step)
        for flag, key, _, _ in OPTIONS:
            p.add_argument(flag, help=f"overrides {key} in the setup file")
        p.add_argument("--run", action="store_true", help="run the script here instead of printing it")
    a = ap.parse_args(argv)

    path = setup_file()
    values = wsf.top_level(path)
    missing, later = [], []
    for flag, key, default, required in OPTIONS:
        attr = flag[2:].replace("-", "_")
        if getattr(a, attr) is None:
            setattr(a, attr, values.get(key) or default)
        if getattr(a, attr) is None and a.step in required:
            (later if key in WRITTEN_BY_IDENTITY else missing).append(key)
    if missing:
        raise SystemExit(f"Fill in {', '.join(missing)} in {shown(path)} first (docs/SETUP.md, step 1).")
    if later:
        raise SystemExit(f"{', '.join(later)} not set yet in {shown(path)}: run `python3 scripts/setup.py identity --run` first "
                         "(it writes them), or ask the Entra admin who ran it.")
    a.repo_source = "config/setup.yaml"
    if a.repo is None and a.step in ("identity", "github"):
        a.repo, a.repo_source = origin_repo(), "this clone's git origin"
        if a.repo is None:
            raise SystemExit(f"This clone has no GitHub origin: fill in github_repo in {shown(path)}.")
    if a.repo is not None and not re.fullmatch(r"[\w.-]+/[\w.-]+", a.repo):
        raise SystemExit(f"github_repo must be <org>/<repo>, not {a.repo!r}")
    if a.approvers and not re.fullmatch(r"[\w.-]+/[\w.-]+", a.approvers):
        raise SystemExit(f"apply_approvers must be <org>/<team>, not {a.approvers!r}")
    script = STEPS[a.step](a)
    if not a.run:
        print("#!/usr/bin/env bash\nset -euo pipefail\n" + script)
        return 0
    return run(script, path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
