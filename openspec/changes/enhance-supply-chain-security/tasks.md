## 1. Documentation

- [x] 1.1 Copy `docs/RISK_MANAGEMENT.md` from temporary location to repository
- [x] 1.2 Update `SECURITY.md` with vulnerability response SLAs and supported version policy
- [x] 1.3 Reference `docs/RISK_MANAGEMENT.md` in `README.md` or `GOVERNANCE.md`

## 2. Release Workflow Improvements

- [x] 2.1 Verify current `actions/attest-build-provenance` configuration in `.github/workflows/release.yml`
- [x] 2.2 Update attestations action to ensure subject digest matches release asset content hash
- [ ] 2.3 Test attestation creation in a PR or branch to verify Scorecard will detect it
- [x] 2.4 Script or manually delete unsigned `skills-1.1.0.zip` asset using GitHub API
- [x] 2.5 Script or manually delete unsigned `skills-1.0.2-beta0.zip` asset using GitHub API
- [x] 2.6 Verify signed releases (v1.1.3, v1.1.4, v1.1.5, v1.1.6) are unaffected
- [ ] 2.7 Trigger a new release to confirm attestations are created and detectable

## 3. Required CodeQL Status Check

- [x] 3.1 Identify current CodeQL job names from `.github/workflows/codeql.yml`
- [x] 3.2 Query existing ruleset for `main` branch using `gh api repos/RichardSlater/skills/rulesets`
- [x] 3.3 Update ruleset to add CodeQL jobs as required status checks
- [ ] 3.4 Verify ruleset change by inspecting via `gh api` or GitHub UI
- [ ] 3.5 Test by creating a PR and confirming CodeQL status is required

## 4. Fuzzing Infrastructure

- [x] 4.1 Create `.github/workflows/fuzzing.yml` workflow for ClusterFuzzLite
- [x] 4.2 Create fuzz target: `fuzz_gitversion_parsing.py` for GitVersion output parsing
- [x] 4.3 Create fuzz target: `fuzz_commit_validation.py` for Conventional Commit validation
- [x] 4.4 Create fuzz target: `fuzz_schema_validation.py` for `.bestpractices.json` validation
- [x] 4.5 Create fuzz target: `fuzz_path_handling.py` for archive path traversal protection
- [ ] 4.6 Test fuzz targets locally to ensure they execute without errors
- [ ] 4.7 Push and verify fuzzing workflow runs on schedule
- [ ] 4.8 Verify ClusterFuzzLite reports to GitHub Issues if a crash is found

## 5. Validation and Cleanup

- [ ] 5.1 Run OpenSSF Scorecard locally to confirm improvements
- [ ] 5.2 Verify provenance attestations are visible via `gh api repos/RichardSlater/skills/attestations`
- [ ] 5.3 Verify unsigned releases are deleted via `gh api repos/RichardSlater/skills/releases`
- [ ] 5.4 Run CodeQL on a test PR to confirm it's a required status check
- [ ] 5.5 Run fuzzing workflow manually to confirm it executes
- [ ] 5.6 Update `.bestpractices.json` if any badge answers changed
- [ ] 5.7 Commit all changes following Conventional Commit format
- [ ] 5.8 Create PR and ensure all checks pass before merging
