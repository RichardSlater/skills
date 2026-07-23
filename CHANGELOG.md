# Changelog

This project is continuously delivered from the default branch. Each delivered state is identified by its Git commit SHA. Versioned GitHub releases use protected `v{major}.{minor}.{patch}` tags on commits reachable from `main`; GitVersion derives and verifies the release version, a read-only job packages the archive, and an approved environment publishes it. The first stable release tag will be `v0.1.0`.

Security fixes are called out explicitly and include the affected behavior and recommended user action. See the Git history and merged pull requests for the complete change record.

## Unreleased

### Added

- CNCF-inspired single-maintainer governance and a security-focused roadmap.
- GitVersion-based SemVer release packaging for protected `v{major}.{minor}.{patch}` tags, with a trusted `main` workflow and environment-gated publishing.
- CodeQL analysis for GitHub Actions and Python.
- OpenSSF Best Practices and Scorecard status badges.
- Architecture, trust-boundary, and security-design documentation.

### Changed

- Run validation and tests on every pull request and every commit to `main`.
- Link the security policy directly to private vulnerability reporting.
- Enforce the `main` repository ruleset with signed commits, pull requests, required validation, and protected history.

### Security

- Added continuous SAST coverage and an explicit private vulnerability-reporting link.
