# OpenSSF Best Practices skill

A skill for a read-only-first assessment of one GitHub repository against the OpenSSF Best Practices Badge criteria, with bounded, approval-gated repository changes.

## Compatibility

Offline assessment requires Python 3.11+ and Git on POSIX with no-follow descriptor-relative access. GitHub CLI/network access are needed only for explicitly approved enrichment. Scorecard requires a reviewed local executable or explicitly approved digest-pinned container.

## Boundaries and outputs

Assessment is strictly read-only and stores transient results outside the target repository: it never formats, validates in place, stages, restores, or otherwise writes target-repository files. Potentially writing tools run only against a temporary assessment copy. Capture and compare content snapshots of HEAD, index and visible files before and after the read-only phase. Ignored paths are explicitly outside snapshot coverage; keep caches outside the tree. After approved apply, report the intended diff instead of claiming an unchanged tree. Private repositories are local-only unless the user gives repository- and destination-scoped disclosure consent. Apply work requires explicit approval naming the repository, `scope: "apply"`, and every repository-relative destination.

Supported BadgeApp automation inputs are `.bestpractices.json` and `.project.d/bestpractices.json`. Generated evidence may use `.bestpractices.dev/`, but activate the supplied `.gitignore.example` in the target repository before writing it there.

The validator uses the pinned BadgeApp schema in `references/schema/`; see its `PROVENANCE.md` for source and update instructions. Helper exits: `0` success, `2` invalid/unsafe input, `3` unavailable tool/service, `4` deadline exceeded.

Scorecard is supporting evidence, not badge compliance. Its runner records immutable artifact provenance and deadline status. Assess GitHub Rulesets first and legacy branch protection second; a GitHub API 403/404 is unavailable evidence, not evidence that either control is absent. Record the endpoint, status, and required maintainer/admin follow-up.

## Offline tests

From the repository root, run `python3 -m unittest discover -s tests/openssf_best_practices`. For release coverage enforcement, install `tests/requirements-openssf-best-practices.txt` and run `python3 -m coverage run --rcfile=tests/.coveragerc -m unittest discover -s tests/openssf_best_practices`, followed by `python3 -m coverage report --rcfile=tests/.coveragerc`; the threshold is 85%.
