# Changelog

This project is continuously delivered from the default branch. Each delivered state is identified by its Git commit SHA, and `main` is protected against non-fast-forward updates; there are currently no separately packaged releases.

Security fixes are called out explicitly and include the affected behavior and recommended user action. See the Git history and merged pull requests for the complete change record.

## Unreleased

### Added

- CodeQL analysis for GitHub Actions and Python.
- OpenSSF Best Practices and Scorecard status badges.
- Architecture, trust-boundary, and security-design documentation.

### Changed

- Run validation and tests on every pull request and every commit to `main`.
- Link the security policy directly to private vulnerability reporting.
- Enforce the `main` repository ruleset with signed commits, pull requests, required validation, and protected history.

### Security

- Added continuous SAST coverage and an explicit private vulnerability-reporting link.
