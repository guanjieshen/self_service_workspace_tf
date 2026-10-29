# Working on terraform/

Read the repository's [AGENTS.md](../AGENTS.md) first. Operators never edit this folder;
they edit `config/`. Everything here turns that YAML into one workspace's resources.

## How a plan is built

```
config/defaults/*.yaml  +  config/workspaces/<name>/*.yaml   (or dev/workspaces/<name>/)
        │
        ▼
config.tf      loads and merges them (maps merge, lists and values replace, null = leave alone)
overrides.tf   which keys a workspace may set; what each setting owns (setting_addresses),
               so that leaving it alone releases it instead of destroying it
checks.tf      plain-language validation (preconditions on terraform_data.config_checks)
access.tf      persona groups and grants;  chargeback.tf  usage policies and tag values
main.tf        module inputs, then one block per module
        │
        ▼
modules/  workspace-settings  personas  compute  budget-policies  catalog
```

One state per workspace. `scripts/tf.sh <workspace> plan` runs it (and the plan guard);
`apply` runs only in the Apply workflow.

## Adding or changing an option

1. **Baseline first.** Add the key to the right `config/defaults/<file>.yaml`, with a
   comment saying what it does and its safe default. A workspace may then set the same
   key in its own file; no extra wiring is needed for the override to be allowed.
2. **Use it** in `main.tf` or a module. If it is a Databricks setting, map it in
   `overrides.tf` (`setting_addresses`) to the resource addresses it owns, so `null`
   releases those addresses. `scripts/tests/test_release.py` checks the mapping.
3. **Validate it** in `checks.tf` if a wrong value is possible: the message names the
   key, the file and what to do.
4. **Test it:** a fixture under `tests/fixtures/` and an assertion in the matching
   `tests/*.tftest.hcl`. For a check, a fixture under `tests/fixtures/invalid/` that breaks
   exactly that rule, and a run in `tests/validation.tftest.hcl`.
5. **Document it** in `config/README.md` (if operators set it), DESIGN.md (if it changes
   the design) and `CHANGELOG.md` (Unreleased; say what the first plan will show).

## The tests' baseline

The tests read `terraform/tests/defaults/`, a copy of `config/defaults/` as released, never
the organization's own `config/defaults/`: an organization changing its baseline must not
break the framework's tests. When you change a baseline file, change it in both places
(the copy keeps the shipped values, for example `required_tags: [LOB, DEPARTMENT, TEAM]`).

## Provider and Terraform gotchas

- **Never put a module-level `depends_on` on `module.personas`** (or any module with data
  sources): every data source is deferred to apply, and permissions that read one are
  planned as replaced. Use the module's outputs (`local.group`) to order grants instead.
  Keep `depends_on = [terraform_data.config_checks]`: the validation tests rely on it.
- **`databricks_workspace_conf` erases keys removed from it** (it resets them). So each
  key is its own resource, and leaving one alone releases it.
- **Conditionals need the same type on both sides.** Pick with `[a, b][cond ? 0 : 1]` or
  iterate keys. `merge(null)` is `{}`. YAML lists and maps arrive as tuples and objects:
  compare with `tolist()` / `tomap()` in tests.
- **`count` and `for_each` must not depend on apply-time values;** pass a bool or known keys.
- **`coalesce()` fails when every argument is null or empty;** use a conditional
  (`x == null ? "" : x`).
- **Tests:** `mock_provider` runs cannot see child-module resources from the root (assert
  on locals, or run the module on its own); after the first failing run in a file the
  rest are skipped; `expect_failures` cannot check which message.
- **Finding a setting's API name:** `GET /api/2.1/settings-metadata` is not complete; also
  check the SDK's settings types and the provider's list of `workspace_conf` keys. Probe
  read-only with `GET /api/2.0/workspace-conf?keys=X`.
- **Unity Catalog needs account groups;** workspace-local groups fail in grants.
