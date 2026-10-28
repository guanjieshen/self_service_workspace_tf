#!/usr/bin/env bash
# scripts/workspaces.py new makes a workspace folder that plans without errors.
# Works on a copy of the repository, so config/workspaces/ is never touched.
#   scripts/tests/test-scaffold.sh        (needs terraform; TERRAFORM=<path> to choose one)
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tf="${TERRAFORM:-terraform}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

tar -C "$root" --exclude .git --exclude .terraform --exclude .state --exclude .plans \
    --exclude config/backend.hcl --exclude terraform/backend_override.tf -cf - config scripts terraform | tar -C "$tmp" -xf -
python3 "$tmp/scripts/workspaces.py" new scaffolded --bu scf --lob SCF --catalog scf_citizen_dev \
  --host https://adb-2222222222222222.2.azuredatabricks.net --account-id 00000000-0000-0000-0000-000000000000 > /dev/null

export TF_DATA_DIR="$tmp/.terraform"
"$tf" -chdir="$tmp/terraform" init -backend=false -input=false > /dev/null
"$tf" -chdir="$tmp/terraform" test -no-color -test-directory=tests/scaffold -var workspace=scaffolded
