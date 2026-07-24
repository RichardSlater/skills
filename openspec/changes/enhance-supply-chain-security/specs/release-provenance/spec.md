## ADDED Requirements

### Requirement: Build provenance attestations are generated for release artifacts
The release pipeline SHALL generate cryptographic build provenance attestations using `actions/attest-build-provenance@v3.0.0` that link each release asset to its exact source commit, build environment, and artifact digest. Attestations SHALL be linked in a way that is detectable by OpenSSF Scorecard.

#### Scenario: Attestation generated for release archive
- **WHEN** a release is published with a `.zip` archive
- **THEN** an attestation is created linking the archive's content digest to the build workflow and source commit

#### Scenario: Attestation generated for checksum files
- **WHEN** a release includes `.sha256` checksum files
- **THEN** attestations are created for both the checksum file and its detached signature

#### Scenario: Attestations queryable via GitHub API
- **WHEN** querying the GitHub Attestations API for the release subject
- **THEN** the attestation is returned with the correct subject digest and build provenance metadata

### Requirement: Legacy unsigned release artifacts are removed
Release artifacts from `v1.1.0` and `v1.0.2-beta0` that lack GPG signatures SHALL be deleted from the GitHub releases to eliminate supply-chain ambiguity.

#### Scenario: Unsigned v1.1.0 artifact deleted
- **WHEN** the migration script runs
- **THEN** the `skills-1.1.0.zip` asset from release `v1.1.0` is deleted

#### Scenario: Unsigned v1.0.2-beta0 artifact deleted
- **WHEN** the migration script runs
- **THEN** the `skills-1.0.2-beta0.zip` asset from release `v1.0.2-beta0` is deleted

#### Scenario: Signed releases remain intact
- **WHEN** the migration completes
- **THEN** releases `v1.1.3`, `v1.1.4`, `v1.1.5`, and `v1.1.6` retain all their signed artifacts

### Requirement: Release workflow produces both GPG signatures and provenance attestations
Every release SHALL produce GPG-signed artifacts AND build provenance attestations. The workflow SHALL ensure both are available before marking the release as complete.

#### Scenario: Release includes both signatures and attestations
- **WHEN** a new release is published
- **THEN** the release includes `.asc` GPG signatures AND GitHub attestations are created via the attestations API

#### Scenario: Attestation subject matches asset digest
- **WHEN** an attestation is created
- **THEN** the attestation subject is the content digest (SHA-256) of the release asset, not a repository ref

## MODIFIED Requirements

### Requirement: Automated release process (from automated-conventional-releases)
The automated release process SHALL be updated to ensure that the `actions/attest-build-provenance` action is configured to produce attestations that are detectable by OpenSSF Scorecard.

#### Scenario: Scorecard detects provenance in subsequent runs
- **WHEN** Scorecard is run after a release with proper attestations
- **THEN** the Signed-Releases check does not report "does not have provenance" for that release
