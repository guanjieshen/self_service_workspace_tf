#!/usr/bin/env bash
# Run Terraform for one workspace (or all of them).
#
#   ./scripts/tf.sh <workspace|all> <validate|plan|apply|destroy|output|force-unlock> [extra terraform args]
#
# <workspace> is a file name, without .yaml, in config/workspaces/ (or dev/workspaces/, the
# workspaces that test the framework itself).
#
# Examples:
#   ./scripts/tf.sh fin-citizen-dev plan
#   ./scripts/tf.sh all plan            # review a baseline change across every workspace
#
# apply and destroy run in the workspace's workflow after a merge; locally they refuse
# unless ALLOW_LOCAL_APPLY=1 (break glass).
#
# plan and apply run scripts/plan-guard.py, which warns about changes that are
# hard to undo (deleted folders, replaced warehouses, disabling legacy access).
# apply then asks you to type the workspace name to continue. In CI, set
# CONFIRM_ENV=<workspace> to approve; without it a flagged apply fails.
# force-unlock <lock ID> releases a state lock left by a run that died (docs/SETUP.md, 11).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tf_dir="$root/terraform"
terraform_bin="${TERRAFORM:-terraform}"

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
[[ $# -ge 2 ]] || usage
workspace="$1"; cmd="$2"; shift 2

ws_roots=("$root/config/workspaces" "$root/dev/workspaces")
list_workspaces() {
  for r in "${ws_roots[@]}"; do
    for f in "$r"/*.yaml; do [[ -f "$f" ]] || continue; f="${f##*/}"; f="${f%.yaml}"; [[ "$f" == _* ]] || echo "$f"; done
  done | sort
}

if [[ "$workspace" == "all" ]]; then
  [[ "$cmd" == "plan" || "$cmd" == "validate" ]] || { echo "'all' supports only plan and validate"; exit 1; }
  status=0
  for e in $(list_workspaces); do
    echo "================ $e ================"
    bash "$0" "$e" "$cmd" "$@" || status=1
  done
  exit $status
fi

ws_root=""
for r in "${ws_roots[@]}"; do
  [[ -f "$r/$workspace.yaml" ]] || continue
  [[ -z "$ws_root" ]] || { echo "$workspace is in both config/workspaces/ and dev/workspaces/: keep one."; exit 1; }
  ws_root="$r"
done
[[ -n "$ws_root" ]] ||
  { echo "No workspace file config/workspaces/$workspace.yaml. Available: $(list_workspaces | tr '\n' ' ')"; exit 1; }

# Changes reach a workspace only through a merged pull request and its workflow.
# Outside GitHub Actions, apply and destroy refuse unless ALLOW_LOCAL_APPLY=1 (break glass:
# CI is down and a workspace needs a fix now; open a pull request with the same change after).
if [[ ("$cmd" == "apply" || "$cmd" == "destroy") && "${GITHUB_ACTIONS:-}" != "true" && "${ALLOW_LOCAL_APPLY:-}" != "1" ]]; then
  echo "Refusing to $cmd outside GitHub Actions: changes are deployed by merging a pull request."
  echo "Plan locally with: ./scripts/tf.sh $workspace plan. Break glass only: ALLOW_LOCAL_APPLY=1."
  exit 1
fi

# Break glass applies to the shared state, the one CI uses: without config/backend.hcl it
# would write a local state the pipeline never sees, and the next CI apply would fight it.
if [[ ("$cmd" == "apply" || "$cmd" == "destroy" || "$cmd" == "force-unlock") && "${GITHUB_ACTIONS:-}" != "true" && ! -f "$root/config/backend.hcl" ]]; then
  echo "Refusing to $cmd without config/backend.hcl: it would use a local state that CI does not share."
  echo "Get config/backend.hcl from the repository (or python3 scripts/setup.py state) first (docs/SETUP.md, step 3)."
  exit 1
fi

# In GitHub Actions: no CLI profiles (the pipeline provides the login), no prompts,
# and state must be shared.
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  export TF_VAR_use_cli_profiles=false TF_IN_AUTOMATION=1
  [[ -f "$root/config/backend.hcl" ]] ||
    { echo "CI needs shared state: create config/backend.hcl with python3 scripts/setup.py state (docs/SETUP.md, step 3)."; exit 1; }
fi

# 1. Pick the backend: shared azurerm state if config/backend.hcl exists, else local files.
export TF_DATA_DIR="$root/.terraform/$workspace"
override="$tf_dir/backend_override.tf"
if [[ -f "$root/config/backend.hcl" ]]; then
  printf 'terraform {\n  backend "azurerm" {}\n}\n' > "$override"
  backend_args=(-backend-config="$root/config/backend.hcl" -backend-config="key=citizen-dev/$workspace.tfstate")
else
  rm -f "$override"
  mkdir -p "$root/.state"
  backend_args=(-backend-config="path=$root/.state/$workspace.tfstate")
fi

"$terraform_bin" -chdir="$tf_dir" init -input=false -reconfigure "${backend_args[@]}" >/dev/null

# 2. Run the command.
vars=(-var "workspace=$workspace" -var "workspaces_dir=$ws_root")
plan_file="$root/.plans/$workspace.tfplan"

# Plan to a file, then check it for changes that are hard to undo.
# Sets guard_status: 0 = nothing risky, 2 = risky changes found.
# Also writes, for CI: .plans/<workspace>.txt (readable plan), .guard.txt (warnings),
# .guard (status) and .changes (number of resources to add, change or destroy).
plan_and_guard() {
  mkdir -p "$root/.plans"
  local base="$root/.plans/$workspace"
  "$terraform_bin" -chdir="$tf_dir" plan "${vars[@]}" -out="$plan_file" "$@"
  "$terraform_bin" -chdir="$tf_dir" show -json "$plan_file" > "$base.json"
  "$terraform_bin" -chdir="$tf_dir" show -no-color "$plan_file" > "$base.txt"
  guard_status=0
  # In CI, preflight ran just before (deploy.yml): its findings let the guard tell a new
  # workspace from one that still uses legacy access. Locally, without them, it flags as usual.
  local evidence=()
  [[ "${GITHUB_ACTIONS:-}" == "true" && -f "$base.preflight-all.txt" ]] && evidence=(--preflight "$base.preflight-all.txt")
  python3 "$root/scripts/plan-guard.py" "${evidence[@]}" < "$base.json" | tee "$base.guard.txt" || guard_status=${PIPESTATUS[0]}
  echo "$guard_status" > "$base.guard"
  python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); print(sum(1 for r in p.get("resource_changes",[]) if r["change"]["actions"] not in (["no-op"],["read"])))' "$base.json" > "$base.changes"
}

# Release what the workspace now leaves unmanaged: remove it from the state, so the apply
# does not destroy it (destroying a setting resets it). Lists the released_addresses output
# of the last plan against the state; prints what it released.
release_unmanaged() {
  local state_list to_release
  # A state that cannot be listed would release nothing, and the apply would destroy what
  # should be left alone: stop instead. A first apply has no state yet: nothing to release.
  local err
  if ! state_list="$("$terraform_bin" -chdir="$tf_dir" state list 2>"$root/.plans/$workspace.state-list.err")"; then
    err="$(cat "$root/.plans/$workspace.state-list.err")"
    [[ "$err" == *"No state file was found"* ]] ||
      { echo "$err"; echo "Could not list the state to release what is left alone; stopping before apply."; exit 1; }
    state_list=""
  fi
  to_release="$(STATE_LIST="$state_list" python3 -c '
import json, os, sys
plan = json.load(open(sys.argv[1]))
prefixes = ((plan.get("planned_values") or {}).get("outputs") or {}).get("released_addresses", {}).get("value") or []
deleted = {r["address"] for r in plan.get("resource_changes", []) if r["change"]["actions"] == ["delete"]}
for addr in os.environ["STATE_LIST"].split("\n"):
    if addr in deleted and any(addr == p or addr.startswith(p + ".") or addr.startswith(p + "[") for p in prefixes):
        print(addr)
' "$root/.plans/$workspace.json")"
  [[ -n "$to_release" ]] || return 1
  echo "Releasing (no longer managed; the workspace keeps its current values):"
  while IFS= read -r addr; do
    echo "  $addr"
    # Called as an `if` condition, so set -e does not apply here: stop explicitly, or the
    # apply would go on to destroy what could not be released.
    "$terraform_bin" -chdir="$tf_dir" state rm "$addr" >/dev/null ||
      { echo "Could not release $addr; stopping before apply."; exit 1; }
  done <<<"$to_release"
}

case "$cmd" in
  validate) "$terraform_bin" -chdir="$tf_dir" validate ;;
  plan)
    plan_and_guard "$@"
    ;;
  apply)
    plan_and_guard "$@"
    if release_unmanaged; then
      echo "Planning again without the released resources."
      plan_and_guard "$@"
    fi
    if [[ $guard_status -ne 0 ]]; then
      if [[ "${CONFIRM_ENV:-}" == "$workspace" ]]; then
        echo "CONFIRM_ENV=$workspace set; continuing."
      elif [[ -t 0 ]]; then
        read -r -p "Type the workspace name ($workspace) to apply anyway: " answer
        [[ "$answer" == "$workspace" ]] || { echo "Cancelled."; exit 1; }
      else
        if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
          echo "::error::The plan guard flagged this apply, and the merged pull request has no allow-risky-changes label. If a person approves the change, add the label to the pull request and re-run this job."
        else
          echo "Refusing to apply risky changes without CONFIRM_ENV=$workspace."
        fi
        exit 1
      fi
    elif [[ -t 0 ]]; then
      read -r -p "Apply this plan to $workspace? Type yes: " answer
      [[ "$answer" == "yes" ]] || { echo "Cancelled."; exit 1; }
    fi
    "$terraform_bin" -chdir="$tf_dir" apply "$plan_file"
    ;;
  destroy)  "$terraform_bin" -chdir="$tf_dir" destroy "${vars[@]}" "$@" ;;
  output)   "$terraform_bin" -chdir="$tf_dir" output "$@" ;;
  # Asks to confirm. Only for a lock whose run is gone: unlocking a running apply corrupts the state.
  force-unlock) "$terraform_bin" -chdir="$tf_dir" force-unlock "$@" ;;
  *) usage ;;
esac
