#!/usr/bin/env bash
# A workspace made the documented way (copy config/workspaces/_example.yaml, fill in bu,
# host and groups) plans without errors, with the account ID from the baseline.
# Works on a copy of the repository, so config/ is never touched.
#   scripts/tests/test-scaffold.sh        (needs terraform; TERRAFORM=<path> to choose one)
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tf="${TERRAFORM:-terraform}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

tar -C "$root" --exclude .git --exclude .terraform --exclude .state --exclude .plans \
    --exclude config/backend.hcl --exclude terraform/backend_override.tf -cf - config scripts terraform | tar -C "$tmp" -xf -
sed -e 's/^bu: xyz /bu: scf /' \
    -e 's#^host: .*#host: https://adb-2222222222222222.2.azuredatabricks.net#' \
    -e 's/^  explorer: null /  explorer: scf-explorers /' \
    "$tmp/config/workspaces/_example.yaml" > "$tmp/config/workspaces/scaffolded.yaml"
# Whatever the organization's baseline holds: the test sets its own account ID.
sed -i.bak 's/^account_id: .*/account_id: 00000000-0000-0000-0000-000000000000/' "$tmp/config/defaults/cost.yaml"

export TF_DATA_DIR="$tmp/.terraform"
"$tf" -chdir="$tmp/terraform" init -backend=false -input=false > /dev/null
"$tf" -chdir="$tmp/terraform" test -no-color -test-directory=tests/scaffold -var workspace=scaffolded
