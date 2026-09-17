## 1. Tune Bubblewrap skill guidance

- [x] 1.1 Add a bootstrap-dependent tooling section that requires an isolated `pre-commit` executable and version probe before running the quality gate.
- [x] 1.2 Document offline-ready pre-commit cases and the required stop-and-report behavior for missing hook repositories, language environments, or sandbox-visible executables.
- [x] 1.3 Document the approved dedicated-cache pattern, including read-only persistent hook content, ephemeral writable runtime state, and rejection of automatic writable global-cache mounts.
- [x] 1.4 Document the escalation alternatives and reporting requirements without changing the standard launcher's no-network, private-home authority boundary.

## 2. Add regression coverage

- [x] 2.1 Add focused automated checks for the required pre-commit preflight, offline failure handling, cache-safety guidance, and unchanged launcher interface.
- [x] 2.2 Verify the checks cover version skew or missing sandbox-visible executables without depending on external network access.

## 3. Validate the change

- [x] 3.1 Run OpenSpec validation for `tune-bubblewrap-pre-commit` and resolve all findings.
- [x] 3.2 Run `pre-commit run --all-files` using the repository-supported host workflow.
- [x] 3.3 Run the repository's relevant compilation and unit-test commands and confirm the working tree contains only intended changes.
