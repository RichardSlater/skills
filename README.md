# Skills

A collection of reusable agent skills for analyzing and improving GitHub repository supply-chain security.

This repository currently focuses on GitHub supply-chain hardening workflows: read-only organization/account analysis and proposal-driven remediation through reviewed pull requests.

## What is included

| Skill | Purpose | Mutates repositories? |
| --- | --- | --- |
| [`github-supply-chain-hardening-analysis`](skills/github-supply-chain-hardening-analysis/SKILL.md) | Discovers repositories for a GitHub organization or user, analyzes supply-chain and secure-SDLC posture, runs OpenSSF Scorecard where available, and writes OpenSpec-style remediation proposals. | No |
| [`github-supply-chain-hardening-remediation`](skills/github-supply-chain-hardening-remediation/SKILL.md) | Applies an approved hardening proposal as file-based changes on a branch, validates the result, and opens a pull request with manual follow-up guidance. | Yes, only after explicit approval |

## Repository layout

```text
skills/
  github-supply-chain-hardening-analysis/
    SKILL.md
    requirements.txt
    scripts/
      discover_tokens.py
      gh_orchestrator.py
  github-supply-chain-hardening-remediation/
    SKILL.md
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

The skill will ask for the GitHub organization or user account to analyze, then run the local read-only analysis flow and write remediation proposals.

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
