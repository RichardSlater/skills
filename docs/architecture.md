# Architecture and security design

## Purpose

This repository distributes reusable agent skills for analyzing and remediating GitHub supply-chain security. Skills are installed directly from the public Git repository and run in the user's existing coding-agent environment.

## Components

- `github-supply-chain-hardening-analysis` discovers repositories, runs read-only checks, and writes remediation proposals.
- `github-supply-chain-hardening-remediation` applies an explicitly approved proposal on a branch and prepares changes for review.
- GitHub Actions validates skill metadata and Python, reviews dependency changes, runs CodeQL, and publishes OpenSSF Scorecard results.

Each skill's `SKILL.md` documents its user-facing inputs, workflow, safety constraints, and outputs. Python command-line interfaces expose additional usage details through `--help`.

## Trust boundaries

The main trust boundaries are:

1. **User to agent:** repository mutation requires explicit user approval; analysis remains read-only.
2. **Agent to GitHub:** scripts use local GitHub CLI or environment authentication and must not print or persist token values.
3. **GitHub to local workspace:** repositories are treated as untrusted input and are cloned into isolated temporary directories for analysis.
4. **Local process to external tools:** Scorecard and other tools receive only the minimum credentials and filesystem access needed for their task.
5. **Pull request to default branch:** validation and repository rules prevent unreviewed direct changes and history rewriting.

## Security assumptions and controls

- Operators protect their local workstation and GitHub CLI credentials.
- Tokens are short-lived or least privilege where possible and are never passed in logged command arguments.
- External command failures and untrusted repository content are handled as data, not as instructions.
- GitHub Actions use explicit least-privilege permissions and immutable action commit pins.
- Dependabot, dependency review, secret scanning with push protection, CodeQL, and Scorecard provide continuous security feedback.
- Security reports use GitHub private vulnerability reporting as documented in [`SECURITY.md`](../SECURITY.md).

## Cryptography and network services

The project does not implement cryptographic algorithms, password storage, or a network service. HTTPS and the Git/GitHub transport provide delivery integrity and confidentiality. Authentication is delegated to GitHub CLI and GitHub APIs rather than implemented by this project.

## Release and change model

The repository is continuously updated and installed from Git. Each delivered state is identified by its Git commit SHA, and the protected `main` branch rejects non-fast-forward updates. User-visible changes are summarized in [`CHANGELOG.md`](../CHANGELOG.md); pull requests and commit history retain the complete reviewable change record.
