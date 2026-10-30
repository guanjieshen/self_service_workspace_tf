#!/usr/bin/env python3
"""Ask a model to summarize a plan and assess its impact.

    scripts/ai-plan-review.py <workspace> [--base <git-ref>] [--endpoint <name>] [--profile <p>] [--request-only]
    scripts/ai-plan-review.py --settings

Settings are in config/setup.yaml: ai_review_host, the workspace whose model
reviews every plan (its adb- URL; null = no review), and ai_review_model. One call to that model (a Unity
Gateway model service), with the pull request and the plan as its only inputs, signed in
as the pipeline (or --profile, a Databricks CLI profile, locally). --endpoint overrides the
model for a local test. --settings prints the settings as name=value lines for the workflow.

Reads .plans/<workspace>.json (from `terraform show -json`), .plans/<workspace>.guard.txt and
.plans/<workspace>.preflight-all.txt, plus the git diff of config/ against --base, and
prints a markdown assessment for the pull request comment.

The result is advice only: it never fails the build. On any error it prints
nothing and explains on stderr. --request-only prints the request instead of
sending it.
"""
import argparse
import base64
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from workspaces import drop_comment  # noqa: E402  (one YAML comment rule for every script)
DEFAULT_MODEL = "system.ai.claude-sonnet-5-5"
MAX_TOKENS = 4000   # the model reasons before it writes; answers in testing used 300 to 600
PROMPT = ".github/ai/plan-review-prompt.md"
MAX_DIFF_CHARS = 30000
MAX_CODE_DIFF_CHARS = 15000   # the framework diff explains a change; the plan shows its effect
MAX_CHANGES_CHARS = 60000
SKIP_TYPES = {"terraform_data"}
# Attributes that are noise for a reviewer.
SKIP_KEYS = {"provider_config", "id", "object_id", "workspace_path", "policy_id", "data_source_id",
             "creator_name", "jdbc_url", "odbc_params", "health", "state", "num_clusters",
             "num_active_sessions", "object_type", "md5"}

KINDS = {
    "databricks_sql_endpoint": "SQL warehouse",
    "databricks_cluster": "Cluster",
    "databricks_cluster_policy": "Cluster policy",
    "databricks_directory": "Folder",
    "databricks_permissions": "Permissions",
    "databricks_entitlements": "Group entitlements",
    "databricks_workspace_conf": "Workspace settings",
    "databricks_budget_policy": "Serverless usage policy",
    "databricks_access_control_rule_set": "Serverless usage policy access",
    "databricks_permission_assignment": "Group assignment to workspace",
    "databricks_sql_global_config": "SQL warehouse settings",
    "databricks_catalog": "Unity Catalog catalog",
    "databricks_schema": "Unity Catalog schema",
    "databricks_grants": "Unity Catalog grants",
    "databricks_workspace_file": "Workspace file",
    "databricks_default_namespace_setting": "Default catalog setting",
    "databricks_disable_legacy_access_setting": "Disable legacy access setting",
    "databricks_disable_legacy_dbfs_setting": "Disable DBFS root and mounts setting",
    "databricks_restrict_workspace_admins_setting": "Restrict workspace admins setting",
    "databricks_compliance_security_profile_workspace_setting": "Compliance security profile setting",
    "databricks_enhanced_security_monitoring_workspace_setting": "Enhanced security monitoring setting",
    "databricks_automatic_cluster_update_workspace_setting": "Automatic cluster update setting",
    "databricks_aibi_dashboard_embedding_access_policy_setting": "Dashboard embedding setting",
    "databricks_aibi_dashboard_embedding_approved_domains_setting": "Dashboard embedding approved domains",
}


def clean(value):
    """Drop nulls, empty values and noise keys, recursively."""
    if isinstance(value, dict):
        if isinstance(value.get("content_base64"), str):  # workspace files: show the text
            value = {**value, "content": base64.b64decode(value["content_base64"]).decode(errors="replace")}
            del value["content_base64"]
        out = {k: clean(v) for k, v in value.items() if k not in SKIP_KEYS}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [clean(v) for v in value if v not in (None, "", [], {})]
    if isinstance(value, str) and value.startswith("{"):
        try:  # policy definitions and similar are JSON strings
            return clean(json.loads(value))
        except ValueError:
            return value
    return value


def action_of(actions):
    if actions == ["create"]:
        return "create"
    if actions == ["update"]:
        return "update"
    if actions == ["delete"]:
        return "delete"
    if "create" in actions and "delete" in actions:
        return "replace"
    return "+".join(actions)


def name_of(rc, values):
    for key in ("name", "path", "directory_path", "policy_name", "display_name"):
        if values.get(key):
            return values[key]
    return rc.get("index", rc["name"])


def planned_changes(plan):
    changes = []
    for rc in plan.get("resource_changes", []):
        actions = rc["change"]["actions"]
        if rc["mode"] != "managed" or rc["type"] in SKIP_TYPES or actions in (["no-op"], ["read"]):
            continue
        before = clean(rc["change"].get("before") or {})
        after = clean(rc["change"].get("after") or {})
        item = {
            "action": action_of(actions),
            "kind": KINDS.get(rc["type"], rc["type"]),
            "name": name_of(rc, after or before),
            "terraform_address": rc["address"],
        }
        if item["action"] == "create":
            item["after"] = after
        elif item["action"] == "delete":
            item["before"] = before
        else:
            item["changed"] = {
                k: {"before": before.get(k), "after": after.get(k)}
                for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)
            }
        changes.append(item)
    return changes


def git(*args):
    out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else f"(git {args[0]} failed: {out.stderr.strip()})"


def setup_file():
    """config/setup.yaml (dev/setup.yaml in the framework's own repository, when it exists)."""
    dev = ROOT / "dev/setup.yaml"
    return dev if dev.exists() else ROOT / "config/setup.yaml"


def setup_value(key):
    """A top-level value of the setup file, or None (null, empty or missing)."""
    path = setup_file()
    text = path.read_text() if path.exists() else ""
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            value = line.split(":", 1)[1].split("#", 1)[0].strip().strip("\"'")
            return None if value in ("", "null", "~") else value
    return None


def load_settings():
    """The review's settings: on when ai_review_host names the workspace that has the model.
    Any workspace the pipeline can sign in to; it need not be one this repository manages."""
    host = (setup_value("ai_review_host") or "").rstrip("/")
    model = setup_value("ai_review_model") or DEFAULT_MODEL
    if host and not re.fullmatch(r"https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net", host):
        raise ValueError(f"ai_review_host in {setup_file().name} must be a workspace URL like https://adb-<id>.<n>.azuredatabricks.net "
                         f"(a custom URL does not serve the API), not {host!r}")
    return {"enabled": bool(host), "host": host, "endpoint": model, "label": model}


def ws_file(workspace):
    """The workspace's file: config/workspaces/<name>.yaml, or dev/workspaces/<name>.yaml for
    the workspaces that test the framework (the same rule as scripts/workspaces.py)."""
    found = [f for f in (ROOT / "config/workspaces" / f"{workspace}.yaml", ROOT / "dev/workspaces" / f"{workspace}.yaml")
             if f.exists()]
    return found[0] if found else ROOT / "config/workspaces" / f"{workspace}.yaml"


def config_diff(base):
    if not base:
        return "(no base ref given)"
    diff = git("diff", base, "--", "config/", "dev/workspaces/")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (diff truncated)"
    return diff or "(no configuration changes in this pull request)"


def code_diff(base):
    """The framework changes that can change what is deployed: the Terraform code (not its
    tests), and the CHANGELOG entry that says why, in plain words."""
    if not base:
        return "(no base ref given)"
    diff = git("diff", base, "--", "terraform/", ":(exclude)terraform/tests/", "CHANGELOG.md")
    if len(diff) > MAX_CODE_DIFF_CHARS:
        diff = diff[:MAX_CODE_DIFF_CHARS] + "\n... (diff truncated)"
    return diff or "(no Terraform code or CHANGELOG changes in this pull request)"


def changed_files(base, workspace):
    if not base:
        return "(no base ref given)"
    lines = []
    for path in git("diff", "--name-only", base).split():
        if path.startswith("config/defaults/"):
            kind = "baseline (affects every workspace)"
        elif re.match(rf"(config|dev)/workspaces/{re.escape(workspace)}\.yaml$", path):
            kind = "this workspace's file"
        elif re.match(r"(config|dev)/workspaces/", path):
            kind = "another workspace's file (not this plan)"
        elif path.startswith("terraform/") and not path.startswith("terraform/tests/"):
            kind = "framework code (can change what every workspace gets; see code_diff)"
        else:
            kind = "code, workflows or docs (no direct workspace change)"
        lines.append(f"- {path}: {kind}")
    return "\n".join(lines) or "(none)"


def strip_comments(text):
    """YAML without comment-only lines, trailing comments or blank lines."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#") or not line.strip():
            continue
        out.append(drop_comment(line))
    return "\n".join(out)


def without_comments(f):
    """A config file's text without comments: # in YAML, <!-- --> in markdown."""
    text = f.read_text()
    return strip_comments(text) if f.suffix == ".yaml" else re.sub(r"(?s)<!--.*?-->", "", text).strip()


def baseline():
    defaults = ROOT / "config/defaults"
    files = sorted(defaults.glob("*.yaml"))
    return "\n\n".join(f"# {f.relative_to(ROOT)}\n{without_comments(f)}" for f in files)


def state_note(plan):
    resources = ((plan.get("prior_state") or {}).get("values") or {}).get("root_module") or {}
    count = len(resources.get("resources", [])) + sum(
        len(m.get("resources", [])) for m in resources.get("child_modules", []))
    managed = count > 0
    return ("Update: Terraform already manages resources in this workspace." if managed
            else "First apply: Terraform manages nothing in this workspace yet, so the whole baseline is created.")


def workspace_field(workspace, key):
    """A top-level value from the workspace's file."""
    text = ws_file(workspace).read_text()
    return next((l.split(":", 1)[1].split("#")[0].strip().strip("\"'") for l in text.splitlines()
                 if l.startswith(f"{key}:")), "")


def gather(workspace, base):
    """The review's inputs for this workspace, from the repository and .plans/ (the plan job)."""
    plans = ROOT / ".plans"
    plan = json.loads((plans / f"{workspace}.json").read_text())
    read = lambda name: (plans / f"{workspace}{name}").read_text().strip() if (plans / f"{workspace}{name}").exists() else ""
    path = ws_file(workspace)
    return {
        "workspace": f"{workspace} ({workspace_field(workspace, 'host')})",
        "state": state_note(plan),
        "changed_files": changed_files(base, workspace),
        "config_diff": config_diff(base),
        "code_diff": code_diff(base),
        "workspace_files": f"# {path.name}\n{without_comments(path)}",
        "baseline": baseline(),
        "planned_changes": planned_changes(plan),
        "plan_guard": read(".guard.txt"),
        "preflight": read(".preflight-all.txt"),
    }


SECTIONS = ["workspace", "state", "changed_files", "config_diff", "code_diff", "workspace_files", "baseline",
            "planned_changes", "plan_guard", "preflight"]


def build_request(inputs):
    """The model request: the prompt, and the inputs as tagged sections (gather(), or an eval case)."""
    changes = json.dumps(inputs["planned_changes"], indent=1)
    if len(changes) > MAX_CHANGES_CHARS:
        changes = changes[:MAX_CHANGES_CHARS] + "\n... (truncated)"
    values = {**inputs, "planned_changes": changes}
    user = "\n\n".join(f"<{k}>\n{values.get(k) or ''}\n</{k}>" for k in SECTIONS)
    return {
        "messages": [
            {"role": "system", "content": (ROOT / PROMPT).read_text()},
            {"role": "user", "content": user},
        ],
        "max_tokens": MAX_TOKENS,
    }


def response_text(resp):
    """The answer text; some models return a list of parts (reasoning + text)."""
    content = resp["choices"][0]["message"]["content"]
    if isinstance(content, str) and content.lstrip().startswith("[{"):
        try:  # a JSON-encoded list of parts
            content = json.loads(content)
        except ValueError:
            pass
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if p.get("type") == "text")
    return content.strip()


def model_review(endpoint, request):
    """One call to a model. Returns the answer."""
    if endpoint.count(".") == 2:  # a Unity Gateway model service, such as system.ai.claude-sonnet-5-5
        cmd = ["databricks", "api", "post", "/ai-gateway/mlflow/v1/chat/completions",
               "--json", json.dumps({"model": endpoint, **request}), "-o", "json"]
    else:  # a model serving endpoint (disabled for databricks- models once Unity Gateway is enforced)
        cmd = ["databricks", "serving-endpoints", "query", endpoint, "--json", json.dumps(request), "-o", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or out.stdout.strip())
    resp = json.loads(out.stdout)
    usage = resp.get("usage") or {}
    print(f"tokens: in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}", file=sys.stderr)
    return response_text(resp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace", nargs="?")
    ap.add_argument("--base")
    ap.add_argument("--endpoint")
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", ""))
    ap.add_argument("--request-only", action="store_true")
    ap.add_argument("--settings", action="store_true")
    args = ap.parse_args()

    if args.settings:  # for the workflow: name=value lines, written to $GITHUB_OUTPUT
        try:
            settings = load_settings()
        except ValueError as e:  # advice only: a wrong setting switches the review off, never the plan
            print(f"::warning::AI review off: {e}", file=sys.stderr)
            settings = {"enabled": False, "label": ""}
        # Only what the workflow reads (deploy.yml: steps.ai.outputs.enabled and .label).
        print(f"enabled={str(settings['enabled']).lower()}")
        print(f"label={settings['label']}")
        return 0
    if not args.workspace:
        ap.error("workspace is required")

    try:
        plan = json.loads((ROOT / ".plans" / f"{args.workspace}.json").read_text())
        if not planned_changes(plan):
            print("AI review skipped: the plan has no changes.", file=sys.stderr)
            return 0
        settings = load_settings()
        request = build_request(gather(args.workspace, args.base))
        if args.request_only:
            print(json.dumps(request, indent=1))
            return 0
        if args.profile:
            os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
        else:  # the review workspace, whatever workspace this plan is for
            os.environ["DATABRICKS_HOST"] = settings["host"]
        print(model_review(args.endpoint or settings["endpoint"], request))
    except Exception as e:  # advice only: never fail the build
        print(f"AI review skipped: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
