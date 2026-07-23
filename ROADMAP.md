# Roadmap

This roadmap describes the intended direction for the next 12 months. It is a
planning document, not a release commitment; priorities may change in response
to security reports, maintainer capacity, or community feedback.

## Scope

The project will continue to provide reusable, safety-first skills for software
engineering, DevOps, and supply-chain security. Skills must preserve explicit
approval boundaries, avoid exposing credentials or private repository data, and
produce evidence that can be reviewed by humans.

The project will not operate hosted security services, retain users' credentials,
or make destructive repository or cloud changes without explicit user approval.

## Next 0–6 months

- Improve the OpenSSF Best Practices assessment skill's evidence, proposal, and
  validation coverage.
- Add supply-chain-focused skills where existing skills.sh offerings do not
  adequately cover the full workflow, starting with SBOM and dependency
  inventory review, and release-artifact verification.
- Document and automate reproducible release packaging, versioning, and release
  notes for this repository.
- Expand tests for security-sensitive orchestration and transformation paths;
  maintain at least 85% measured coverage for the scoped OpenSSF Best Practices
  Python sources.

## Next 6–12 months

- Evaluate provenance and attestation verification guidance for published
  artifacts, including how agents should verify rather than merely claim
  provenance.
- Add dependency-risk triage guidance that distinguishes repository evidence,
  package-manager metadata, and operational follow-up.
- Improve examples and documentation for secure use of each skill, including
  least-privilege GitHub authentication and review workflows.
- Reassess this roadmap with contributors and publish an updated plan.

## How to contribute

Propose roadmap changes through a GitHub issue or pull request. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md) for the
project's contribution and decision-making processes.
