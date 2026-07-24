# Security Policy

## Supported versions

This repository is maintained from the default branch. The following versions are supported with security updates:

- **Latest release** — Full support for critical and high severity vulnerabilities
- **Previous release** — Support for critical severity vulnerabilities only
- **Older releases** — No guaranteed support; users should upgrade to the latest release

Security fixes are made against the latest default-branch state. When a vulnerability affects older releases, backports may be published for supported versions on a best-effort basis.

## Reporting a vulnerability

Please do **not** report security vulnerabilities in public GitHub issues.

Instead, [report the vulnerability privately through GitHub](https://github.com/RichardSlater/skills/security/advisories/new). If private reporting is unavailable, contact the repository owner privately and include enough information to reproduce and assess the issue.

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

## Vulnerability response SLAs

The maintainer commits to the following response time targets for privately reported vulnerabilities:

| Severity | Initial Response    | Resolution Target       |
|----------|---------------------|-------------------------|
| Critical | Within 24 hours     | Fix and advisory within 48 hours |
| High     | Within 48 hours     | Fix and advisory within 7 days |
| Medium   | Within 5 days       | Fix and advisory within 30 days |
| Low      | Within 10 days      | Fix and advisory within 60 days   |

*Initial Response* means acknowledging receipt, confirming the security advisory was received, and requesting any additional information needed to reproduce the issue.

*Resolution* means publishing a fix (patch release or commit), creating a GitHub security advisory, and coordinating public disclosure with the reporter.

These are target SLAs and may vary based on complexity, reporter cooperation, and whether the vulnerability involves third-party dependencies. The maintainer will communicate proactively if timelines need adjustment.

## GitHub-based response process

Private reports are handled through the GitHub security advisory created from
the private reporting link above. The sole maintainer follows this process:

1. Confirm receipt in the advisory and request only the information needed to
   reproduce and assess the report.
2. Triage impact, affected versions, exploitability, and whether credentials or
   private repository data may be involved.
3. Track investigation, mitigation, and reporter communication in the private
   advisory rather than public issues or pull requests.
4. Prepare and validate a fix in a restricted branch or private fork when
   disclosure before remediation would create avoidable risk.
5. Coordinate disclosure with the reporter, publish the GitHub security
   advisory when it is safe to do so, and document affected versions and user
   action in release notes.
6. Credit reporters in the advisory unless they request anonymity.

This process defines how future reports are handled; it does not assert a
historical response-time record. Do not disclose a vulnerability publicly until
the maintainer and reporter have had a reasonable opportunity to investigate
and remediate it.

## Secret handling

Never paste GitHub tokens, cloud credentials, private keys, or private repository contents into issues, pull requests, discussions, or chat transcripts. If a secret is exposed, revoke and rotate it immediately.
