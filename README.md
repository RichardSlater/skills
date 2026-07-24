# Skills

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13724/badge)](https://www.bestpractices.dev/projects/13724)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/RichardSlater/skills/badge)](https://securityscorecards.dev/viewer/?uri=github.com/RichardSlater/skills)
[![skills.sh](https://skills.sh/b/RichardSlater/skills)](https://skills.sh/RichardSlater/skills)

A collection of reusable agent skills for analyzing and improving GitHub repository supply-chain security.

This repository provides GitHub supply-chain hardening workflows and an OpenSSF Best Practices Badge assessment skill with schema-backed, approval-gated proposals.

## What is included

| Skill | Purpose | Mutates repositories? |
| --- | --- | --- |
| [`github-supply-chain-hardening-analysis`](skills/github-supply-chain-hardening-analysis/SKILL.md) | Discovers repositories for a GitHub organization or user, analyzes supply-chain and secure-SDLC posture, runs OpenSSF Scorecard where available, and writes OpenSpec-style remediation proposals. | No |
| [`github-supply-chain-hardening-remediation`](skills/github-supply-chain-hardening-remediation/SKILL.md) | Applies an approved hardening proposal as file-based changes on a branch, validates the result, and opens a pull request with manual follow-up guidance. | Yes, only after explicit approval |
| [`openssf-best-practices`](skills/openssf-best-practices/SKILL.md) | Assesses a GitHub repository against OpenSSF Best Practices Badge criteria, validates schema-backed proposals, and uses Scorecard only as supporting evidence. | Assessment: no. Apply: only after explicit bounded approval. |

## Repository layout

```text
skills/
  github-supply-chain-hardening-analysis/
    SKILL.md
    requirements.txt
    scripts/
      discover_tokens.py
      gh_orchestrator.py
      scorecard_runner.py
  github-supply-chain-hardening-remediation/
    SKILL.md
    scripts/
      scorecard_runner.py
  openssf-best-practices/
    SKILL.md
    scripts/
    references/
tests/
  openssf_best_practices/
```

## Quick start

### 1. Install the skills

```bash
npx skills add https://github.com/RichardSlater/skills
```

The installer presents the available skills to add. To install a specific skill directly, pass the skill name with the skills CLI option, for example:

```bash
npx skills add https://github.com/RichardSlater/skills --skill github-supply-chain-hardening-analysis
```

### 2. Authenticate with GitHub

Ensure the GitHub CLI is installed and logged in:

```bash
gh auth login
gh auth status
```

Do **not** paste GitHub tokens into chat, issues, pull requests, or logs. The analysis skill discovers local authentication metadata without printing token values.

### 3. Run the analysis skill in your agent

Start your coding agent and invoke the skill command:

```text
/github-supply-chain-hardening-analysis
```

The skill will ask for the GitHub organization or user account to analyze, then run the local read-only analysis flow and write remediation proposals. OpenSSF Scorecard runs locally when installed; otherwise the skill can pull and run `ghcr.io/ossf/scorecard:latest` with Docker, Podman, or nerdctl. It can safely source authentication from `gh auth token` in process memory and forward it as `GITHUB_AUTH_TOKEN` without putting the token in command arguments.

Generated proposals are written under the analysis skill's configured output directory. Treat proposals as potentially sensitive because they may include repository security posture and remediation details.

## Security model

The analysis skill is intentionally read-only. It must not push branches, open issues, create pull requests, mutate repository settings, or write secrets to disk.

The remediation skill is intentionally review-based. It applies approved file changes on a branch and opens a pull request only after explicit user approval. Repository settings such as branch protection, rulesets, secret scanning, and organization policies remain manual administrator follow-up tasks.

## Development guidelines

- Keep skill instructions explicit, auditable, and safe-by-default.
- Never log or commit GitHub tokens, cloud credentials, or private repository contents.
- Prefer least-privilege GitHub App or fine-grained tokens over broad classic PATs.
- Keep repository-scale loops inside local scripts instead of agent context windows.
- Add tests or validation steps for scripts whenever behavior changes.
- Update this README and relevant templates when adding new skills.

## Documentation and roadmap

- [Governance](GOVERNANCE.md) explains project roles and decision-making.
- [Roadmap](ROADMAP.md) describes the next year's security-focused priorities.
- [Security policy](SECURITY.md) explains private reporting and GitHub-based response handling.
- [Support](SUPPORT.md) explains how to get non-security help.

## Releases

A push to protected `main` automatically evaluates Conventional Commit messages.
`fix` releases a patch, `feat` releases a minor, and `!` or `BREAKING CHANGE:`
releases a major; valid `build`, `chore`, `ci`, `docs`, `refactor`, `style`, and
`test` commits do not publish a release on their own. GitVersion calculates from
the immutable `v1.0.2` baseline, a read-only job packages the exact triggering
commit, and only the `release` environment publishing job may create the tag and
GitHub release. Generated GitHub release notes describe each publication;
[`CHANGELOG.md`](CHANGELOG.md) remains a curated project overview. See
[`docs/release-operations.md`](docs/release-operations.md) for repository
controls, recovery, and rollback.

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

Good first contributions include:

- Clarifying skill instructions.
- Adding validation for proposal generation.
- Improving generated remediation guidance.
- Expanding safe detection coverage for additional ecosystems.
- Improving documentation and examples.

## Security

Please do not report vulnerabilities in public issues. See [`SECURITY.md`](SECURITY.md) for supported versions and responsible disclosure instructions.

## License

This project is licensed under the [MIT License](LICENSE).
