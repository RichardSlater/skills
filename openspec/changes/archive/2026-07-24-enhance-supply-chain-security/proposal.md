## Why

The skills repository has a strong OpenSSF Scorecard baseline (7.0) but lacks practical supply-chain security controls that protect downstream consumers. Specifically: release provenance is not detected by Scorecard, CodeQL analysis is not enforced as a required status check, and there is no fuzzing infrastructure to catch input-parsing vulnerabilities. Additionally, unsigned release artifacts from legacy releases create ambiguity about supply-chain integrity.

These gaps matter because agent skills are installed directly from GitHub without traditional package-level integrity checks, making cryptographic attestations and continuous fuzzing critical for establishing trust.

## What Changes

- Enable build provenance attestations so Scorecard detects them (fixes the "missing provenance" finding for all releases)
- Delete unsigned release artifacts from `v1.1.0` and `v1.0.2-beta0` to eliminate supply-chain ambiguity
- Add CodeQL analysis as a **required status check** in the branch protection ruleset so every merged commit is scanned
- Integrate ClusterFuzzLite with fuzz targets for critical input-parsing functions
- Add fuzzing schedule to the weekly automation cycle
- Update SECURITY.md with vulnerability handling SLA targets for Silver badge progression
- Document risk management rationale for accepting lower scores on Code-Review, Contributors, and Maintained checks

## Capabilities

### New Capabilities
- `release-provenance`: Cryptographic build provenance attestations for all release artifacts, linked to their exact source commits and build environment
- `required-codeql`: CodeQL SAST analysis enforced as a required status check in branch protection rulesets
- `continuous-fuzzing`: Integrated fuzzing infrastructure using ClusterFuzzLite to catch edge cases in input parsing, path handling, and schema validation

### Modified Capabilities
- `automated-conventional-releases`: The release pipeline will now produce both GPG signatures AND build provenance attestations; legacy unsigned release artifacts will be cleaned up

## Impact

- `.github/workflows/release.yml` - Updated to ensure provenance attestations are properly linked to release assets
- `.github/workflows/fuzzing.yml` - New workflow for ClusterFuzzLite integration
- `docs/RISK_MANAGEMENT.md` - New document explaining security trade-offs
- `SECURITY.md` - Enhanced vulnerability response documentation for Silver badge criteria
- Branch protection ruleset for `main` - CodeQL added as required status check
- Existing releases `v1.1.0` and `v1.0.2-beta0` - Unsigned artifacts deleted via GitHub API
