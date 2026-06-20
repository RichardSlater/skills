# Security Policy

## Supported versions

This repository is maintained from the default branch. Security fixes are made against the latest default-branch state unless a maintainer explicitly announces a supported release branch.

## Reporting a vulnerability

Please do **not** report security vulnerabilities in public GitHub issues.

Instead, use GitHub's private vulnerability reporting if it is enabled for this repository. If private reporting is not available, contact the repository owner privately and include enough information to reproduce and assess the issue.

Please include:

- A concise description of the vulnerability.
- Affected files, scripts, or skill behavior.
- Steps to reproduce or a minimal proof of concept.
- Expected impact and any known mitigations.
- Whether tokens, private repository data, or other secrets may have been exposed.

## Scope

Security-sensitive issues include, but are not limited to:

- Token or credential disclosure.
- Instructions that could cause an agent to leak secrets or private source code.
- Unsafe mutation of repositories without explicit approval.
- GitHub Actions or dependency supply-chain vulnerabilities.
- Path traversal, command injection, or unsafe shell execution in scripts.
- Generated remediation guidance that weakens repository security.

## Handling expectations

Maintainers will aim to:

1. Acknowledge valid reports promptly.
2. Triage severity and affected scope.
3. Prepare a fix or mitigation.
4. Credit reporters when appropriate and requested.

Do not disclose the vulnerability publicly until maintainers have had a reasonable opportunity to investigate and remediate it.

## Secret handling

Never paste GitHub tokens, cloud credentials, private keys, or private repository contents into issues, pull requests, discussions, or chat transcripts. If a secret is exposed, revoke and rotate it immediately.
