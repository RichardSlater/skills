# OpenSSF Best Practices skill

A skill for a read-only-first assessment of one GitHub repository against the OpenSSF Best Practices Badge criteria, with bounded, approval-gated repository changes.

## Compatibility

Python 3.11+, GitHub CLI, and network access are required. Scorecard assessment additionally requires the pinned local executable or Podman, Docker, or nerdctl.

## Boundaries and outputs

Assessment is read-only and stores transient results outside the target repository. Private repositories are local-only unless the user gives repository- and destination-scoped disclosure consent. Apply work requires explicit approval naming every repository-relative destination.

Supported BadgeApp automation inputs are `.bestpractices.json` and `.project.d/bestpractices.json`. Generated evidence may use `.bestpractices.dev/`, but activate the supplied `.gitignore.example` in the target repository before writing it there.

The validator uses the pinned BadgeApp schema in `references/schema/`; see its `PROVENANCE.md` for source and update instructions. Helper exits: `0` success, `2` invalid/unsafe input, `3` unavailable tool/service, `4` deadline exceeded.

Scorecard is supporting evidence, not badge compliance. Its runner records immutable artifact provenance and deadline status.

## Offline tests

From the repository root, run `python3 -m unittest discover -s tests/openssf_best_practices`. For release coverage enforcement, install `tests/requirements-openssf-best-practices.txt` and run `python3 -m coverage run --rcfile=tests/.coveragerc -m unittest discover -s tests/openssf_best_practices`, followed by `python3 -m coverage report --rcfile=tests/.coveragerc`; the threshold is 85%.
