## 1. Establish the release contract

- [x] 1.1 Add representative Conventional Commit fixtures for scoped and unscoped `fix`, `feat`, `!`, `BREAKING CHANGE:`, non-releasing types, malformed headers, and mixed-increment precedence.
- [x] 1.2 Add automated classification tests proving `fix` maps to patch, `feat` maps to minor, breaking syntax maps to major, the highest increment wins, and all other non-breaking types produce no release.
- [x] 1.3 Add tests proving non-releasing commits remain in the range and are included when a later qualifying commit triggers a release.

## 2. Configure and verify GitVersion

- [x] 2.1 Update `GitVersion.yml` with Conventional Commit major, minor, patch, and no-bump expressions while retaining the `v` tag prefix and documented initial-version policy.
- [x] 2.2 Pin the GitVersion setup/execution mechanism used by GitHub Actions and ensure it receives complete commit and tag history.
- [x] 2.3 Exercise GitVersion against temporary histories covering no existing tag, an existing release tag, mixed increments, breaking changes, and non-releasing ranges.
- [x] 2.4 Rehearse GitVersion against the current repository history and record or resolve any mismatch with the immutable `v1.0.2` release baseline.

## 3. Validate Conventional Commit metadata

- [x] 3.1 Add a pull-request check that validates the canonical squash-merge title against the repository's Conventional Commit policy without requesting write permissions.
- [x] 3.2 Reuse the release-contract fixtures to verify the pull-request validator and GitVersion classification cannot disagree on valid headers and release signals.
- [x] 3.3 Update contributing guidance with accepted types, scopes, `!` and `BREAKING CHANGE:` syntax, examples, and the squash-merge expectation.
- [x] 3.4 Document the required branch-ruleset status check and squash-merge repository setting for maintainers.

## 4. Automate read-only release planning and packaging

- [x] 4.1 Change the release workflow trigger from maintainer-supplied tag dispatch to pushes on protected `main`, and add workflow-level release concurrency with cancellation disabled.
- [x] 4.2 Set workflow-level `permissions: {}` and give the planning/packaging job only `contents: read` with `persist-credentials: false` checkout of the exact triggering SHA.
- [x] 4.3 Execute GitVersion in the planning job and validate the emitted SemVer, `v{major}.{minor}.{patch}` tag, previous tag, release-required decision, and triggering SHA before exposing job outputs.
- [x] 4.4 Make a no-signal run complete successfully without uploading a release artifact or requesting any write permission.
- [x] 4.5 Package the release archive from the exact planned checkout, version its filename from validated GitVersion output, and upload it as a short-lived workflow artifact.

## 5. Publish with job-scoped least privilege

- [x] 5.1 Attach the publishing job to the `release` environment and grant `contents: write` only on that job, with no workflow-wide or planning-job write permission.
- [x] 5.2 Download the prepared archive without checking out or executing repository code, and expose `GH_TOKEN` only to the publication step that requires it.
- [x] 5.3 Revalidate immediately before mutation that the planned SHA remains reachable from `main`, the version and tag are well formed, and existing tag/release state is safe.
- [x] 5.4 Create an annotated release tag targeting the exact planned SHA without moving or replacing an existing tag.
- [x] 5.5 Create the GitHub release with the validated title, immutable tag, generated notes, and versioned archive without replacing existing assets.
- [x] 5.6 Implement idempotent handling for an already-complete release and recovery when the expected tag exists at the expected SHA but release creation previously failed.
- [x] 5.7 Fail closed when a tag points to another commit, a release conflicts with expected state, or any planned output differs from the publication-time checks.

## 6. Configure release notes and documentation

- [x] 6.1 Add or refine `.github/release.yml` so generated notes present user-facing changes clearly and can exclude dependency-only or explicitly skipped pull requests.
- [x] 6.2 Update `README.md` and `CHANGELOG.md` to describe automatic Conventional Commit releases, no-release types, and the distinction between generated release notes and the curated changelog.
- [x] 6.3 Document immutable retry and recovery procedures, including the prohibition on moving, deleting, or reusing published release tags.
- [x] 6.4 Document required `v*` tag ruleset, trusted GitHub Actions actor, `release` environment, and automatic-versus-approval-gated environment behavior without recommending a PAT.

## 7. Validate and activate the automation

- [x] 7.1 Add static workflow assertions that workflow permissions are empty, read-only jobs have only `contents: read`, and only the publishing job has `contents: write`.
- [x] 7.2 Run repository tests, actionlint, dependency/security checks, and Conventional Commit/GitVersion fixtures against the completed workflow changes.
- [ ] 7.3 Verify repository ruleset evidence for required pull-request validation, squash merging, protected `v*` tag creation, immutable tags, and the trusted publishing actor.
- [x] 7.4 Run a non-mutating rehearsal on current `main` and inspect the calculated version, no-release/release decision, exact SHA, archive contents, generated-note range, and effective job permissions.
- [ ] 7.5 Enable automatic publication only after the rehearsal and repository-setting checks pass, then verify a non-releasing change produces no tag and a qualifying change produces one correctly targeted release.
- [x] 7.6 Confirm rollback can disable the automatic trigger and restore manual dispatch without deleting or moving any published tag.
