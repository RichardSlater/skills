## Context

The skills repository publishes agent skills for direct GitHub installation. The current release workflow produces GPG-signed artifacts but Scorecard's Signed-Releases check reports "does not have provenance" for all releases because the `actions/attest-build-provenance` action's output is not being detected properly. Additionally, two legacy releases (`v1.1.0`, `v1.0.2-beta0`) have only unsigned `.zip` files, creating supply-chain ambiguity.

CodeQL runs on PR and push to main but is not a required status check, meaning 6 of 26 recent commits were merged without SAST analysis. There is no fuzzing infrastructure to catch edge cases in input parsing.

The repository is maintained by a single person, making traditional peer code review infeasible. This design focuses on automated, verifiable controls rather than human-dependent processes.

## Goals / Non-Goals

**Goals:**
- Make build provenance detectable by OpenSSF Scorecard for all future releases
- Eliminate unsigned legacy release artifacts
- Ensure every merged commit has been scanned by CodeQL
- Detect and report fuzzing-discovered bugs via GitHub Issues automatically
- Document security trade-offs transparently
- Move toward Silver badge criteria through improved vulnerability response documentation

**Non-Goals:**
- Force peer code review for a single-maintainer project
- Publish to npm or GitHub Packages (no value for direct-GitHub-install workflow)
- Recruit multiple organizations to contribute (not practical for a personal project)
- Integrate with OSS-Fuzz (too heavy for ClusterFuzzLite's lightweight approach)

## Decisions

### 1. Provenance Attestation Configuration

**Decision:** The `actions/attest-build-provenance@v3.0.0` action is already invoked in the release workflow but Scorecard does not detect the attestations. The issue is that attestations must be linked to specific artifact digests/URIs that Scorecard can query. The current implementation passes `subject-path` but the attestation is likely being created with a GitHub ref instead of the artifact's content digest.

**Rationale:** According to the [GitHub Attestations API](https://docs.github.com/en/rest/attestations), attestations are queried by subject digest or GitHub resource URI. Scorecard expects attestations to be linked to release assets by their content hash. The fix is to ensure the attestation subject matches the exact asset uploaded to the release.

**Alternative considered:** Manually download and re-upload attestations — rejected because this adds complexity and the GitHub attestations API should handle this if configured correctly.

### 2. Legacy Release Artifact Cleanup

**Decision:** Delete unsigned `.zip` files from releases `v1.1.0` and `v1.0.2-beta0` using the GitHub REST API (`DELETE /repos/{owner}/{repo}/releases/assets/{asset_id}`).

**Rationale:** These releases cannot be retroactively signed with the current GPG key (the signing workflow didn't exist then). Removing them eliminates ambiguity: Scorecard will see only the signed releases (v1.1.3, v1.1.4, v1.1.5, v1.1.6) and will no longer count unsigned assets. This does not affect users who have already installed these versions since the skills are installed from git tags, not release assets.

**Alternative considered:** Leave them as-is — rejected because Scorecard explicitly penalizes unsigned release artifacts in the "last 5 releases," and they serve no current purpose.

### 3. CodeQL Required Status Check

**Decision:** Add CodeQL analysis as a required status check in the branch protection ruleset for `main`. The check name should match the GitHub Actions job name: `Analyze (actions)` and `Analyze (python)`.

**Rationale:** Without a required status check, a maintainer could merge a PR while CodeQL is still running or if there is a transient failure. Making it required ensures every merged commit has been scanned. This is a configuration change in the GitHub Ruleset, not a workflow change.

**Implementation:** Use `gh api` to update the ruleset rules for `main` to add `required_status_checks` with the CodeQL job contexts.

### 4. ClusterFuzzLite Integration

**Decision:** Add ClusterFuzzLite with Python fuzz targets for:
- GitVersion output parsing (`analyze_best_practices.py` parsing logic)
- Conventional Commit message validation (`release.yml` planning logic)
- Proposal schema validation (`validate_best_practices.py`)
- Artifact packaging path handling (`.zip` creation, path traversal)

**Rationale:** ClusterFuzzLite is the lightweight, GitHub-native option that integrates directly with GitHub Actions. It reports findings as GitHub Issues, requires minimal setup, and runs continuously on a schedule. It's specifically designed for open-source projects that don't need the full OSS-Fuzz infrastructure.

**Fuzz target structure:**
```python
def fuzz_parse_gitversion(data: bytes):
    # Parse untrusted GitVersion output
    pass

def fuzz_validate_commit_message(data: bytes):
    # Validate Conventional Commit format
    pass
```

Schedule: Weekly on Monday (same as Scorecard) to minimize CI load.

### 5. Vulnerability Response Documentation

**Decision:** Update `SECURITY.md` to include:
- Vulnerability response time targets (e.g., "critical: 48 hours, high: 7 days")
- Supported version policy (e.g., "latest release + one previous")
- Security contact options (GitHub private vulnerability reporting, email)
- Disclosure process and embargo policy

**Rationale:** Silver badge criteria require documented vulnerability handling processes with response time commitments. The current `SECURITY.md` has basic reporting instructions but lacks operational SLAs.

## Risks / Trade-offs

### Risk 1: Provenance API may not expose attestations to Scorecard

**[Risk] → Mitigation:** The GitHub Attestations API was released recently and Scorecard may not fully support it yet. If attestations still aren't detected after fixing the subject-path, document this as a Scorecard limitation and focus on the GPG signing (which Scorecard does detect). The provenance still benefits downstream consumers even if Scorecard doesn't see it.

### Risk 2: Deleting release artifacts may break users who rely on direct asset downloads

**[Risk] → Mitigation:** The skills installation workflow uses `npx skills add` which clones from git tags, not release assets. No active users should be affected. Document the removal in `CHANGELOG.md` as a breaking change for edge cases.

### Risk 3: Required CodeQL check could block merges if CodeQL has transient failures

**[Risk] → Mitigation:** GitHub status checks can be retried by maintainers. If CodeQL fails, the maintainer can re-run the workflow. This is a standard CI/CD operational pattern and is acceptable.

### Risk 4: Fuzzing may produce false positives or low-value findings

**[Risk] → Mitigation:** ClusterFuzzLite reports to GitHub Issues, which the maintainer can triage. Fuzzing infrastructure is low-cost when run on a weekly schedule (not continuous). If it produces noise, the workflow can be adjusted or disabled without impact.

## Migration Plan

1. **Phase 1: Documentation** - Add `docs/RISK_MANAGEMENT.md`, update `SECURITY.md`
2. **Phase 2: Release Workflow Fixes** - Fix provenance attestation configuration, delete unsigned legacy artifacts via API
3. **Phase 3: Branch Protection** - Add CodeQL as required status check
4. **Phase 4: Fuzzing** - Add ClusterFuzzLite workflow and fuzz targets
5. **Phase 5: Validation** - Run Scorecard after changes to verify improvements

**Rollback:** Each phase is independent and can be rolled forward or back:
- If provenance still isn't detected, revert to GPG-only signing (no loss of security)
- If CodeQL required check is too strict, remove it from ruleset (still runs, just not required)
- If fuzzing produces excessive noise, disable the workflow (no operational impact)

## Open Questions

None. All decisions have clear implementation paths based on existing GitHub features and well-documented tools.
