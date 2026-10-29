#!/usr/bin/env bash
# Run every test. No workspace, credentials or network needed (Terraform uses mocked providers).
#
#   ./scripts/test.sh              all suites
#   ./scripts/test.sh terraform    one suite: terraform | python | node | scaffold
#
# CI runs the same suites in the "Tests" job of .github/workflows/checks.yml.
# TERRAFORM=<path> picks the Terraform binary (default: terraform on the PATH).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tf="${TERRAFORM:-terraform}"
suite="${1:-all}"

run() { [[ "$suite" == all || "$suite" == "$1" ]]; }

if run terraform; then
  echo "== Terraform: terraform/tests/*.tftest.hcl"
  export TF_DATA_DIR="$root/.terraform/_test"
  "$tf" -chdir="$root/terraform" init -backend=false -input=false > /dev/null
  "$tf" -chdir="$root/terraform" test -no-color
  unset TF_DATA_DIR
fi
if run python; then
  echo "== Python: scripts/tests/test_*.py"
  python3 -m unittest discover -s "$root/scripts/tests"
fi
if run node; then
  echo "== Node: .github/scripts/tests/*.test.js"
  node --test "$root"/.github/scripts/tests/*.test.js
fi
if run scaffold; then
  echo "== Scaffold: a workspace file copied from _example.yaml"
  TERRAFORM="$tf" "$root/scripts/tests/test-scaffold.sh"
fi
echo "All tests passed."
