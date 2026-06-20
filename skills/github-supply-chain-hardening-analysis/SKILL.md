---
name: github-supply-chain-hardening-analysis
description: Analyze a GitHub organization or personal account for supply-chain and hardened SDLC concerns, then generate OpenSpec-style remediation proposals for each active non-fork repository.
---

# github-supply-chain-hardening-analysis

## Purpose

This skill performs read-only GitHub organization or personal repository supply-chain and hardened SDLC analysis while preserving the agent context window.

It:

- Discovers available GitHub tokens from `GITHUB_TOKEN` and `gh auth token` without printing token values.
- Prints only token metadata: source, non-secret token identifier, account, visible orgs, OAuth scopes, and repository permission summaries.
- Discovers repositories owned by either a GitHub organization or a GitHub personal account.
- Skips archived repositories and forks, reporting each breakdown separately.
- Performs read-only GitHub supply-chain and hardened SDLC analysis.
- Delegates repository-scale work to colocated `scripts/gh_orchestrator.py`.
- Generates one OpenSpec-style remediation proposal per active repository.
- Runs OpenSSF Scorecard on each analyzed repository and uses the results as evidence for remediation priorities.
- Saves generated proposals under `./proposals/` relative to the skill directory unless another output directory is provided.
- Avoids loading repository-scale loops, clone contents, tokens, and file traversal into the LLM context window.

## When to use this skill

Use this skill when the user asks to:

- Review GitHub organization or personal repositories for supply-chain security.
- Harden GitHub repositories at scale.
- Identify missing secure-SDLC controls.
- Generate GitHub remediation proposals.
- Prepare OpenSpec proposals for repository governance, GitHub Actions, dependency security, secrets, access control, release integrity, and AI-agent workflow risks.

## Inputs required

This skill requires exactly one repository owner target:

- `github_org_name`: GitHub organization name, or
- `github_user_name`: GitHub user account for owned personal repositories.

The operator does **not** need to paste a token into chat. Tokens are discovered by local scripts from:

- `GITHUB_TOKEN` environment variable.
- `gh auth token` for the active GitHub CLI account.

The token should preferably be one of:

- A GitHub App installation token.
- A fine-grained personal access token with the minimum required read permissions.
- A GitHub CLI token for the account that owns or can read the target repositories.

Avoid recommending broad classic personal access tokens. The token only needs enough visibility to enumerate and clone/read repositories that should be analyzed.

## Security constraints

The agent and scripts must:

- Never ask the user to paste a token into chat.
- Never print an auth token.
- Never write an auth token to disk.
- Never pass an auth token as a command-line argument in normal use.
- Never include secrets in generated proposals.
- Never create branches.
- Never create pull requests.
- Never open issues.
- Never push commits.
- Never mutate repository settings.
- Never delete files outside the temporary clone workspace.
- Treat cloned source code as sensitive.
- Only write generated proposal files to the configured local output directory.

`discover_tokens.py` may print a short `token_id` derived from a SHA-256 digest prefix only so multiple discovered tokens can be distinguished. It must not print the token value or any reversible token material.

## Installation/layout notes

This skill is self-contained for `skills.sh` installation. Required runtime assets are colocated under the skill directory:

```text
github-supply-chain-hardening-analysis/
  SKILL.md
  requirements.txt
  scripts/
    discover_tokens.py
    gh_orchestrator.py
```

When executing commands, first change into this skill directory so `scripts/...`, `requirements.txt`, and `./proposals` resolve correctly.

If dependencies are missing, install from the colocated requirements file in an isolated environment where possible:

```bash
python -m pip install -r requirements.txt
```

## Execution flow

The agent must:

1. Do not enumerate repositories directly in the LLM context window.
2. Do not loop over repository files natively as an agent.
3. Change into the installed skill directory, then run token discovery locally:

   ```bash
   cd /path/to/github-supply-chain-hardening-analysis
   python scripts/discover_tokens.py
   ```

4. Review the printed metadata with the user if token choice or target visibility is ambiguous. Use only token source labels such as `GITHUB_TOKEN` or `gh auth token`; never request token values.
5. Invoke the background Python orchestrator using the shell tool.
6. Prefer `--token-source auto`, `--token-source env`, or `--token-source gh` over passing a token.
7. Read the script’s final JSON summary from stdout.
8. Report the summary to the user.

Organization command pattern:

```bash
python scripts/gh_orchestrator.py --org "$github_org_name" --token-source auto
```

Personal repository command pattern:

```bash
python scripts/gh_orchestrator.py --user "$github_user_name" --token-source auto
```

If discovery shows multiple available tokens and the target is visible to only one source, select it explicitly:

```bash
python scripts/gh_orchestrator.py --org "$github_org_name" --token-source env
python scripts/gh_orchestrator.py --user "$github_user_name" --token-source gh
```

Optional flags:

```bash
python scripts/gh_orchestrator.py \
  --org "$github_org_name" \
  --token-source auto \
  --output-dir ./proposals \
  --max-concurrency 5 \
  --repo-timeout-seconds 600 \
  --clone-depth 1
```

For a limited confidence test that clones and analyzes only one active repository:

```bash
python scripts/gh_orchestrator.py --org "$github_org_name" --token-source auto --max-repositories 1
python scripts/gh_orchestrator.py --user "$github_user_name" --token-source auto --max-repositories 1
```

For a dry-run repository discovery check without cloning or writing proposals. Dry-run output lists the active non-fork repositories selected after archived/fork filtering and any repository limit:

```bash
python scripts/gh_orchestrator.py --org "$github_org_name" --token-source auto --dry-run
python scripts/gh_orchestrator.py --user "$github_user_name" --token-source auto --dry-run
```

## OpenSSF Scorecard evidence

The analysis must treat OpenSSF Scorecard as a primary evidence source, not just a workflow to add. For each repository:

1. Run Scorecard using the command-line interface (or the public web viewer for public repositories), for example:
   ```bash
   scorecard --repo github.com/owner/repository --format json --show-details > scorecard.json
   ```
2. Record the overall score and a summary of each check result, paying special attention to checks rated `Critical` or `High` risk.
3. Map failing or low-scoring Scorecard checks to concrete remediations:

   | Scorecard check | Typical remediation |
   |-----------------|---------------------|
   | Branch-Protection | Ruleset or branch protection requiring PRs, reviews, status checks, creation/deletion restrictions, and force-push restrictions. |
   | Code-Review | Required approving reviews, CODEOWNERS review for sensitive paths, dismiss stale approvals. |
   | Dependency-Update-Tool | Dependabot or Renovate version update configuration. |
   | Signed-Releases | Release signing, SLSA provenance, or artifact attestations. |
   | Token-Permissions | Least-privilege `GITHUB_TOKEN` permissions at workflow and job level. |
   | Dangerous-Workflow | Remove unsafe `pull_request_target`, script-injection patterns, and untrusted checkout usage. |
   | Pinned-Dependencies | Pin GitHub Actions, container images, and package/tool references to immutable commit SHAs or hashes. |
   | SAST | Add CodeQL or equivalent static analysis workflow. |
   | Vulnerabilities | Triage open OSV/GitHub Advisory Database findings; update or remove vulnerable dependencies. |
   | Security-Policy | Add or improve `SECURITY.md`. |
   | Fuzzing | Recommend OSS-Fuzz, ClusterFuzzLite, or language-native fuzzing where applicable. |
   | CI-Tests | Ensure required CI test status checks block merge. |
   | Binary-Artifacts | Remove or justify committed executable/compiled artifacts. |
   | Webhooks | Review webhook secrets and least-privilege event scopes. |
   | License | Verify an OSI-approved license is declared. |

   In addition to direct remediations, map Scorecard findings to the broader OpenSSF ecosystem:
   - **Branch-Protection / Code-Review / Token-Permissions** controls are good candidates for enforcement with **OpenSSF Allstar**.
   - **Signed-Releases** and **Artifact-Attestations** map to **SLSA Build Level 3** provenance and **Sigstore/cosign** signing.
   - **Vulnerabilities** maps to **OSV** and the **OSV-Scanner** action.
   - **Dependency-Update-Tool** and **Security-Policy** map to a `SECURITY-INSIGHTS.yml` declaration.
   - Inconclusive vulnerability findings may be clarified with **OpenVEX** statements.

4. Include the Scorecard JSON output path and a summarized check table in the generated proposal.
5. Prioritize remediation proposals by Scorecard risk rating (`Critical`, then `High`, then `Medium`/`Low`), intersected with repository criticality and recent activity.

## 2026 GitHub hardened SDLC concern areas

Tell the script to inspect and generate proposals for the following areas where applicable.

### Repository governance

- Branch protection or repository rulesets.
- Required pull request reviews.
- Required status checks.
- Required code scanning results before merge.
- Required dependency review before merge.
- Linear history, signed commits, or signed tags where appropriate.
- Force-push and branch deletion restrictions.
- CODEOWNERS presence and coverage.
- SECURITY.md presence.
- Repository visibility and ownership metadata.
- Stale repositories that are active but appear abandoned.
- Repositories that should be archived but are not.

### GitHub Actions hardening

- Third-party actions pinned to full-length commit SHAs.
- Avoidance of mutable references such as `@main`, `@master`, or broad version tags where high assurance is required.
- Minimal `GITHUB_TOKEN` permissions at workflow and job level.
- Default read-only permissions where possible.
- Explicit `id-token: write` only where OIDC is required.
- OIDC federation instead of long-lived cloud credentials.
- Avoidance of plaintext secrets in workflow files.
- Safe handling of untrusted pull requests.
- Dangerous `pull_request_target` usage.
- Command/script injection from untrusted GitHub context values.
- Action allowlisting or pinning policy recommendations.
- Artifact upload/download integrity concerns.
- Cache poisoning risks.
- Build artifact provenance and artifact attestations.
- Deployment environments with approvals and protected secrets.
- Self-hosted runner usage, including isolation, ephemerality, and repository restrictions.

### Dependency and package supply chain

- Dependency graph readiness (required by Scorecard Vulnerabilities and Dependabot checks).
- Dependabot alerts readiness.
- Dependabot security updates.
- Dependabot version updates.
- Dependency review workflow presence and required-status-check integration.
- Lockfile presence and freshness.
- Scorecard-generated dependency findings acted upon.
- Package manager hygiene for:
  - npm
  - pnpm
  - yarn
  - NuGet
  - Maven
  - Gradle
  - pip
  - Poetry
  - Pipenv
  - Cargo
  - Go modules
  - Docker
  - GitHub Actions
- Dependency confusion risks.
- Private registry configuration risks.
- Malicious package or typosquatting exposure indicators.
- SBOM generation opportunities.
- License policy gaps.
- Unsupported or deprecated dependency indicators.
- OpenSSF Scorecard evidence and remediation mapping.

### OpenSSF ecosystem alignment

- OpenSSF Scorecard evidence and remediation mapping.
- OpenSSF Allstar deployment opportunity (organization-wide policy enforcement for branch protection, dependency updates, security settings, etc.).
- OpenSSF Security Insights (`SECURITY-INSIGHTS.yml`) presence and accuracy.
- SLSA/Sigstore provenance target level and release signing practices.
- OSV-Scanner workflow opportunity for ecosystems not fully covered by Dependabot.
- OpenVEX usage for declaring non-exploitable CVEs.
- OpenSSF Best Practices Badge (CII) passing criteria where a project wants external attestation.
- S2C2F secure consumption framework alignment for organization-level dependency consumption policy.

### Secrets and credential hygiene

- Secret scanning recommendations.
- Push protection recommendations.
- Custom secret patterns where organization-specific credentials exist.
- `.env`, private key, token, certificate, and credential file detection.
- Hardcoded credentials in configuration files.
- Cloud credential references.
- Cloud credential rotation recommendations.
- Replacement of static cloud secrets with OIDC where applicable.

### Code security and vulnerability management

- CodeQL or equivalent code scanning presence.
- SARIF upload support where third-party scanners are used.
- SAST workflow presence.
- Container scanning where Dockerfiles or container build workflows exist.
- IaC scanning where Terraform, Kubernetes, Helm, or similar files exist.
- Security alert triage expectations.
- Vulnerability remediation workflow expectations.

### Release, provenance, and build integrity

- Signed releases or release provenance.
- GitHub artifact attestations.
- SLSA-style provenance recommendations.
- Reproducible build opportunities.
- Protected release workflows.
- Tag protection or tag rulesets.
- Package publishing workflow hardening.
- Trusted publishing where supported by the ecosystem.
- Least-privilege package publishing tokens.
- Environment-scoped release secrets.

### Access control and collaboration model

- Outside collaborator review.
- Team-based access rather than direct user grants.
- Least-privilege repository roles.
- Required 2FA or enterprise SSO assumptions.
- Fine-grained PAT or GitHub App preference over broad classic PATs.
- Bot and machine-user access review.
- CODEOWNERS-aligned review routing.

### SDLC documentation and process

- Threat model presence.
- Secure development policy.
- Contribution guidelines.
- Responsible disclosure policy.
- Security contact path.
- Incident response references.
- Risk acceptance documentation.
- Architecture decision records for security-sensitive changes.
- Evidence artifacts suitable for audit or compliance review.

### AI and agentic development risks

- AI-generated code without human review.
- Prompts, generated code, or automation scripts committed with secrets.
- Agent credentials scoped too broadly.
- Agents allowed to mutate repositories without review.
- Lack of human approval before security-sensitive changes.
- Untrusted code execution by agents in CI.
- Generated dependency changes without dependency review.
- Skill or agent instructions that could cause prompt-injection or supply-chain exposure.

## Output expectations

The agent should expect:

- A token discovery JSON summary from colocated `scripts/discover_tokens.py` with no token values.
- Concise progress logs from colocated `scripts/gh_orchestrator.py`.
- A final JSON summary on stdout.
- One proposal file per successfully analyzed repository.
- Proposal files written to:

```text
./proposals/{safe_repo_name}.json
```

The agent’s final response to the user must include:

- Target type (`organization` or `user`).
- Target name.
- Number of repositories discovered.
- Number of archived repositories skipped.
- Number of forks skipped.
- Number of active non-fork repositories analyzed.
- Number of proposals generated.
- Number of repositories failed.
- Number of repositories timed out.
- Output directory.
- A clear statement that no repository changes were made.

## Failure handling

The agent must report:

- Missing token from both `GITHUB_TOKEN` and `gh auth token`.
- Authentication failure.
- Organization or user not found.
- Target not visible to the selected token source.
- API rate limiting.
- Clone failures.
- Timeout failures.
- Proposal validation failures.
- Repositories skipped and why, including separate archived and fork counts.

The agent should not retry destructive actions because none are allowed.
