# Risk Management

This document records deliberate security trade-offs and operational decisions made for the skills repository.

These choices accept lower OpenSSF Scorecard scores where practical constraints make the criterion infeasible or low-value, while actively pursuing improvements that reduce real security risk.

---

## Accepted Trade-Offs (Lower Score, Acceptable Risk)

### CRR.1 — Code Review (Score: 0)

**Decision:** Not pursued.

**Rationale:** This is a single-maintainer repository. The OpenSSF Code-Review check requires that approximately the last 30 merged changesets have human approval reviews. With only one active contributor, requiring independent review is operationally infeasible.

**Mitigating controls:**
- Strict **Conventional Commit** enforcement via CI prevents accidental or malformed merges
- **CodeQL SAST** runs on every PR and push, providing automated security analysis
- **Scorecard supply-chain analysis** runs weekly to detect workflow regressions
- All changes go through **PRs** (never pushed directly to `main`), creating an auditable trail
- Release workflow requires commit to be reachable from `main` before publishing

**Residual risk:** A compromised maintainer account could merge malicious code without detection. This risk is inherent to any single-maintainer project and is not unique to this repository. The mitigating controls above reduce the window of opportunity and increase detection likelihood.

---

### Contributors (Score: 3)

**Decision:** Not pursued.

**Rationale:** The Contributors check requires recent contributors from at least 3 different organizations. This repository is a personal project by a single engineer. There is no remediation step that improves actual security — forcing artificial organizational diversity would be counterproductive.

**Residual risk:** Minimal. Single-maintainer projects are common and well-understood in the open-source ecosystem. Trust is established through transparent, auditable processes rather than organizational diversity.

---

### Maintained (Score: 0, resolves after 90 days)

**Decision:** Acceptable for early stage.

**Rationale:** The project was created on 2026-06-20. The Maintained check does not assess projects younger than 90 days. This will automatically resolve to a positive score once sufficient commit history exists.

**Mitigating control:** Active development is ongoing with regular commits and releases. The project includes clear roadmap and governance documentation.

---

### Packaging (Score: ?)

**Decision:** Not pursued.

**Rationale:** The skills framework installs skills directly from the GitHub repository using `npx skills add`. There is no value in publishing to an npm registry or GitHub Packages because:
- Skills are cloned, not imported as libraries
- Users need the full directory structure, documentation, and scripts
- The skills CLI handles version resolution via git tags

Publishing to a package hub would add operational complexity without reducing security risk.

**Residual risk:** None. Direct GitHub cloning with tag-pinned versions is a valid and common distribution mechanism for agent skills and similar tooling.

---

## Actively Pursued Improvements (Higher Score, Real Security Value)

### 1. Release Provenance and Cleanup

**Current state:** 3 of 5 recent releases have signed artifacts. 2 older releases (`v1.1.0`, `v1.0.2-beta0`) have unsigned `.zip` only. All releases lack detected provenance attestations.

**Planned work:**
- Fix `actions/attest-build-provenance` configuration so Scorecard detects attestations properly
- Delete unsigned release artifacts from `v1.1.0` and `v1.0.2-beta0` to eliminate ambiguity
- Ensure future releases consistently produce both GPG signatures and build provenance attestations

**Security value:** Build provenance enables downstream consumers to verify the complete build pipeline — from source commit to published artifact. This is a stronger guarantee than GPG signing alone because it cryptographically links the artifact to its exact source state.

---

### 2. CodeQL as Required Status Check

**Current state:** CodeQL runs on PR and push to `main`, but is not a **required** status check in the branch protection ruleset. 6 of 26 recent commits were merged without CodeQL analysis.

**Planned work:**
- Add CodeQL analysis as a required status check in the branch protection ruleset for `main`
- This ensures every merged commit has been analyzed for vulnerabilities

**Security value:** Without the requirement, a maintainer could accidentally merge a PR while CodeQL is still running or if there is a transient failure. Making it required eliminates this possibility and ensures every change has been scanned.

---

### 3. ClusterFuzzLite Integration

**Current state:** No fuzzing infrastructure.

**Planned work:**
- Add ClusterFuzzLite workflow for Python fuzzing
- Create fuzz targets for critical input-parsing functions: GitVersion parsing, Conventional Commit validation, proposal schema validation, artifact packaging
- Schedule continuous fuzzing via GitHub Actions

**Security value:** Fuzzing is particularly valuable for this repository because:
- Scripts parse untrusted input (Conventional Commit messages, GitVersion output, project schemas)
- File path handling and archive creation could be vulnerable to injection or traversal attacks
- Automated fuzzing catches edge cases that manual testing misses

ClusterFuzzLite is the lightweight option that integrates directly with GitHub Actions and reports findings as GitHub issues.

---

### 4. OpenSSF Best Practices Badge: Silver

**Current state:** Passing badge achieved.

**Planned work:**
- Review Silver criteria and identify achievable improvements
- Enhance vulnerability response documentation (response time guarantees, version support matrix)
- Improve security review practices documentation
- Ensure all Passing-level criteria remain met through ongoing operations

**Security value:** Silver criteria require concrete operational security practices (vulnerability handling SLAs, security review processes, documented release process) that go beyond basic passing requirements. Meeting these criteria improves the repository's actual security posture, not just the badge.

---

### 5. Branch Protection: Stricter Ruleset

**Current state:** Ruleset requires 1 reviewer, but this is symbolic for a single-maintainer project.

**Planned work:**
- Increase required reviewers to **2** where feasible (enables contribution from others when they occur)
- Ensure **no bypass actors** are configured (Scorecard deducts points if any bypass exists)
- Keep all other Tier 4/5 requirements active

**Security value:** A no-bypass ruleset means that *everyone* is subject to the same controls, including the owner. This prevents accidental or malicious circumvention of protections by an administrator.

---

## Risk Assessment Summary

| Control | Scorecard Impact | Real Security Impact | Decision |
|---------|:---------------:|:-------------------:|----------|
| Code Review | 0 → 10 | Low (single maintainer) | Accept lower score |
| Contributors | 3 → 10 | None (organizational) | Accept lower score |
| Maintained | 0 → 10 | Moderate (project age) | Accept lower score (resolves automatically) |
| Packaging | ? → 10 | None (direct GitHub install) | Accept lower score |
| Provenance Attestations | +high | High (supply chain) | **Implement** |
| Required CodeQL | 9 → 10 | Moderate (missed scans) | **Implement** |
| Fuzzing | 0 → 10 | Moderate (input parsing) | **Implement** |
| Silver Badge | 5 → 7 | Moderate (operational rigor) | **Pursue** |
| Stricter Branch Protection | 8 → 10 | Moderate (bypass prevention) | **Implement** |

---

## Governance

This document is reviewed biannually alongside the [Security Policy](../SECURITY.md) and [Roadmap](../ROADMAP.md). Changes require:
- Update to this document explaining the rationale
- Update to `.bestpractices.json` if the change affects badge answers
- PR review and merging following the same controls documented here

**Last updated:** 2026-07-24
