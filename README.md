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

### 1. Clone the repository

```bash
git clone git@github.com:RichardSlater/skills.git
cd skills
```

### 2. Prepare Python dependencies for analysis

The analysis skill has colocated Python dependencies:

```bash
cd skills/github-supply-chain-hardening-analysis
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Authenticate with GitHub

Use the GitHub CLI or an existing `GITHUB_TOKEN`. Do **not** paste tokens into chat, issues, pull requests, or logs.

```bash
gh auth login
# or set GITHUB_TOKEN in your shell environment
```

The analysis scripts are designed to discover tokens locally and print only non-secret metadata.

### 4. Discover available token metadata

```bash
python scripts/discover_tokens.py
```

### 5. Run a read-only discovery check

For an organization:

```bash
python scripts/gh_orchestrator.py --org <github-org> --token-source auto --dry-run
```

For a personal account's owned repositories:

```bash
python scripts/gh_orchestrator.py --user <github-user> --token-source auto --dry-run
```

### 6. Generate remediation proposals

```bash
python scripts/gh_orchestrator.py \
  --org <github-org> \
  --token-source auto \
  --output-dir ./proposals \
  --max-concurrency 5
```

Generated proposals are written under the selected output directory. The default `./proposals` directory is ignored by Git because proposals may contain sensitive repository analysis context.

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
