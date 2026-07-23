# Governance

## Purpose

This document defines how the project makes decisions, who is responsible for
maintaining it, and how contributors can participate. It follows the CNCF
principles of transparent, documented decision-making, contributor participation,
and clear accountability, adapted to this single-maintainer project.

## Scope and roles

- **Sole maintainer:** [Richard Slater](https://github.com/RichardSlater), as
  recorded in [CODEOWNERS](.github/CODEOWNERS), is responsible for project
  direction, security triage, releases, and final decisions.
- **Contributors:** anyone who opens an issue, proposes a change, reviews a
  change, or improves documentation. Contributors do not receive repository
  access merely by contributing.

The maintainer may add or remove maintainers by updating this document and
`CODEOWNERS` in a reviewed pull request. A future maintainer group should define
its decision and voting rules in this document before taking on that role.

## Decision-making

1. Proposals start as a GitHub issue or pull request, except security reports,
   which follow [SECURITY.md](SECURITY.md).
2. Discussion and rationale belong in the issue or pull request so decisions are
   publicly reviewable.
3. The sole maintainer makes the final decision after considering technical,
   security, compatibility, and maintenance impact.
4. Contributors who disagree may request reconsideration with new evidence or
   propose an alternative in a separate issue or pull request.

Changes affecting credentials, repository mutation, GitHub Actions permissions,
or supply-chain controls require explicit security review by the maintainer.

## Releases and project assets

Releases are made from reviewed changes on `main` using the documented release
workflow. The maintainer is responsible for verifying release notes and assets.

To reduce single-person continuity risk, the maintainer must keep recovery
instructions and required project access arrangements available to a designated
trusted successor. The identity of that successor and access details are kept
out of the public repository. This is a required operating practice, not a claim
that continuity arrangements have already been tested.

## Changes to this governance

Changes to this document require a pull request with a rationale and approval by
the sole maintainer. Material changes should be announced in the pull request
and release notes when they affect contributors or users.
