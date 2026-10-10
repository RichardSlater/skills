# Verification and migration notes

## Validated scope

- Public skill helpers, references, dependency locks and documentation.
- Existing operator edits to Bubblewrap/README and new malicious-intent/pre-commit skills included.
- Ignored `.pi/skills` and `.pi/prompts` corrected locally only, by operator decision.
- Default skill metadata, Python compilation, relevant workflow semantics, tests and pre-commit checked.

## Results

- Bubblewrap: 127 tests across analysis, remediation, tmux, Bubblewrap contracts, release contracts and Best Practices; 126 passed, one optional GitVersion rehearsal skipped because its executable is not configured.
- Best Practices scoped coverage: 89%; required threshold remains 85%.
- Actionlint v1.7.12: changed validation workflow passed.
- Pre-commit: YAML, whitespace, Ruff and Markdown checks passed.
- Fully redacted gitleaks v8.30.1 snapshot scan: zero findings, including new publication files.
- Pinned offline Docker validation: analysis/remediation/tmux suites passed; tmux runtime integration skipped because the slim image lacks tmux. Git-dependent suites were validated in Bubblewrap instead.
- New main/delta OpenSpec specifications passed strict validation.

## Reproduction and limitations

Synthetic regressions cover sequence-form actions, multiline interpolation, nested manifests, Docker digests, linked/special input, output confinement, mandatory consent, incomplete discovery, process-group limits, container cleanup and content snapshots. No private repository credentials were used for external Scorecard/API testing. Real privileged GitHub settings were not changed.

An additional release-contract failure was reproduced against unchanged HEAD: tests required obsolete action SHAs. Assertions now require full immutable pins for the same actions, retaining permission/signing checks; the release workflow itself is unchanged.

Content snapshots explicitly exclude ignored paths and are not forensic proof of zero writes. Containers have bounded cleanup grace in addition to execution deadlines. Artifact checksums match upstream releases; this is not a claim of independent publisher-signature verification.

## Reviewed artifact identity

- Scorecard v5.5.0: `ghcr.io/ossf/scorecard@sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795`.
- Docker test image: `docker.io/library/python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`; operator-approved read-only host mount, disposable copy, no network/credentials, dropped capabilities, resource limits and cleanup.
- Gitleaks v8.30.1 Linux archive SHA-256: `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.
- Actionlint v1.7.12 Linux archive SHA-256: `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8`.
- Runtime and coverage dependencies resolved from applicable released PyPI versions and installed offline from hash-verified wheels; platform release hashes are retained in the lock files.

## CLI migration

Best Practices discovery is offline by default. Online discovery, fetch, account inventory and Scorecard use an operator-supplied repository/destination-bound consent record; private-flag omission is no longer a consent bypass. Repository-local reports require exact path approval and active ignore rules. Apply-file requires a clean tree, approved destination and safe external source. See the skill for record schemas and commands. Hardening Scorecard containers require `--allow-container`; argv token values are rejected without echoing them.
