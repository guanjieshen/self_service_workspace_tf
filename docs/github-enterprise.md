# Installing in your organization's GitHub

How to move this project into your own GitHub organization, including **GitHub Enterprise**, and get it deploying to your own Azure Databricks workspaces.

> **Short version.** Import the repository into your GitHub, then run the same setup steps as everyone else ([SETUP.md](SETUP.md), steps 1–9). You get your own identity and federated credentials. Nothing from another installation is reused, and no workflow needs editing.

## The flow, step by step

| Step | What you do | What to watch for on GitHub Enterprise |
| --- | --- | --- |
| 1 | Fill in [`config/setup.yaml`](../config/setup.yaml): tenant, subscription, state storage, `github_repo`, `pipeline_name` | A release has these blank. Fill in your own values, never another installation's |
| 2 | Push the repository into your organization | It gets **new owner and repository IDs**, so its OIDC subject prefix is new. Credentials made for another repository do not work for this one |
| 3 | `setup.py state`: the storage account, the container, `config/backend.hcl` | Entra sign-in only, no shared keys |
| 4 | `setup.py identity`: an **app registration**, the two federated credentials for your repository, and Storage Blob Data Contributor on the state container | The script reads your repository's subject prefix through the GitHub API, and uses the github.com issuer (see [Which GitHub you have](#which-github-you-have)) |
| 5 | `setup.py github`: repository variables, the `allow-risky-changes` and `drift` labels, the `apply-approval` environment, branch protection on `main` | On a paid plan, **required reviewers and branch protection work**: set `apply_approvers` in `config/setup.yaml`. `TERRAFORM_RUNNER` and `CHECKS_RUNNER` (self-hosted runners) are set by hand, below |
| 6 | Databricks account, by hand: add the identity, make it workspace admin, give it **Billing admin** | The same on every GitHub |
| 7 | Entra groups, synced to the Databricks account | Including `{prefix}_platform_admins`, **with members** (preflight warns while it is empty) |
| 8 | Baseline decisions: `account_id`, the chargeback tags, the Git allowlist | Add your GitHub host to `settings.git.allowed_urls` if it is not github.com |
| 9 | Onboard each workspace: one file and a pull request | No workflow edits |

## Which GitHub you have

What changes is **where GitHub's OIDC tokens come from** (the issuer) and **what they say** (the subject). Entra must match both exactly.

> **Check before relying on this.** The issuer URLs and options below come from GitHub's and Microsoft's documentation and change over time. Confirm them against the current docs for your GitHub plan before you set up the federated credentials.

| Your GitHub | Issuer | What to do |
| --- | --- | --- |
| **GitHub Enterprise Cloud on github.com** (most common) | `https://token.actions.githubusercontent.com` | Nothing extra: `setup.py identity` works as is |
| …with a **unique issuer URL** turned on for the enterprise | `https://token.actions.githubusercontent.com/<enterprise-slug>` | Both federated credentials must use it. The script uses the default issuer, so create the credentials by hand ([SETUP.md, step 4](SETUP.md#setting-it-up-in-the-azure-portal)) or change `ISSUER` in `scripts/setup.py` |
| …with a **custom OIDC subject template** | as above | The script reads the prefix, but a fully custom template can change the `:pull_request` and `:ref:refs/heads/main` endings. Check the subjects a run actually sends, and match the credentials to them |
| **GitHub Enterprise Cloud with data residency** (`<name>.ghe.com`) | A `ghe.com` issuer, not the github.com one | Create the credentials by hand with your issuer. Also add `https://<name>.ghe.com/` to the Git allowlist |
| **GitHub Enterprise Server** (self-hosted) | Your server's own issuer (`https://<your-host>/_services/token`) | Create the credentials by hand with your issuer. Your server must be reachable from Entra for it to read the issuer's keys. Point `gh` at your host (`GH_HOST`) for `setup.py github`, and add your host to the Git allowlist |

In every case the subjects keep the same shape: `<prefix>:pull_request` for plans and `<prefix>:ref:refs/heads/main` for applies, drift checks and retirements. Read your prefix with:

```bash
gh api repos/<org>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix
```

## Self-hosted runners

The workspaces usually sit behind private networking, so the jobs that run Terraform need runners that can reach them and the state storage.

| Repository variable | What it sets | Example |
| --- | --- | --- |
| `TERRAFORM_RUNNER` | Where plans, applies, drift checks and retirements run | `["self-hosted", "databricks"]` |
| `CHECKS_RUNNER` | Where formatting, tests and the router run (no network access needed) | `"ubuntu-latest"` |

Both take a JSON `runs-on` value. Set them under the repository's **Settings > Secrets and variables > Actions > Variables**. Keep the runners up to date: the pinned actions run on Node 24, which needs a recent runner version. See [github-actions.md](github-actions.md) for what runs where.

## Checking it works

1. Open a pull request that changes one workspace's file. The **Plan** job should sign in and post a plan comment.
2. If it fails at sign-in with `AADSTS70021: No matching federated identity record found`, the issuer or a subject does not match: compare the federated credentials with your issuer and prefix.
3. Merge it. The **Apply** job signs in as `main` and deploys.

For the identity itself (what the app registration needs, the portal steps, the errors), see [SETUP.md, step 4](SETUP.md#4-the-pipeline-identity).
