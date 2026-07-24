## ADDED Requirements

### Requirement: Automatic release evaluation on main

The release system SHALL evaluate each successful change that reaches the protected `main` branch without requiring a maintainer to calculate or enter a version or tag.

#### Scenario: Qualifying change reaches main

- **WHEN** a change containing a release signal reaches `main`
- **THEN** the system automatically begins release calculation for the exact resulting commit

#### Scenario: Manual version input is unavailable

- **WHEN** the automated release workflow starts
- **THEN** it does not require or accept a maintainer-supplied version or release tag

### Requirement: Conventional Commit release mapping

The release system SHALL apply Conventional Commits SemVer semantics to commits since the latest valid release tag: `fix` increments the patch version, `feat` increments the minor version, and either a type or scope followed by `!` or a `BREAKING CHANGE:` footer increments the major version. Other commit types SHALL NOT independently cause a release.

#### Scenario: Fix produces a patch release

- **WHEN** the unreleased commit range contains `fix(parser): handle an empty manifest` and no higher release signal
- **THEN** the calculated version increments the patch component

#### Scenario: Feature produces a minor release

- **WHEN** the unreleased commit range contains `feat(skills): add a validator` and no breaking release signal
- **THEN** the calculated version increments the minor component

#### Scenario: Exclamation marker produces a major release

- **WHEN** the unreleased commit range contains a valid Conventional Commit with `!` before the description separator
- **THEN** the calculated version increments the major component regardless of its commit type

#### Scenario: Breaking footer produces a major release

- **WHEN** the unreleased commit range contains a valid `BREAKING CHANGE:` footer
- **THEN** the calculated version increments the major component

#### Scenario: Highest increment wins

- **WHEN** the unreleased commit range contains more than one release signal
- **THEN** the system selects major over minor and minor over patch

#### Scenario: Scope does not affect increment

- **WHEN** two otherwise equivalent release commits differ only by Conventional Commit scope
- **THEN** they produce the same release increment

### Requirement: Non-releasing changes complete safely

The release system SHALL complete successfully without creating a tag, release, or release asset when the unreleased commit range contains no `fix`, `feat`, or breaking-change signal.

#### Scenario: Chore-only change reaches main

- **WHEN** the unreleased commit range contains only valid `chore` commits
- **THEN** the workflow reports that no release is required and performs no repository mutation

#### Scenario: Documentation and CI changes accumulate

- **WHEN** only non-releasing commits such as `docs`, `test`, `build`, or `ci` have reached `main`
- **THEN** no release is created and those commits remain in the unreleased range for the next qualifying release

### Requirement: Conventional Commit input validation

The repository SHALL validate the commit metadata used for release determination against the Conventional Commits structure and SHALL provide an actionable failure for malformed release metadata.

#### Scenario: Valid Conventional Commit metadata

- **WHEN** a proposed change uses valid Conventional Commit metadata
- **THEN** the validation check passes and its release signal can be evaluated predictably

#### Scenario: Malformed release metadata

- **WHEN** a proposed change uses malformed metadata that cannot be classified according to the repository's Conventional Commit policy
- **THEN** the validation check fails with guidance identifying the required format before the change is eligible to reach `main`

### Requirement: GitVersion is the version authority

The release system SHALL execute GitVersion against complete repository history and existing `v{major}.{minor}.{patch}` tags, and SHALL use its calculated SemVer as the release version.

#### Scenario: Calculate from the latest release

- **WHEN** GitVersion evaluates commits after the latest valid release tag
- **THEN** it produces the next version using the configured Conventional Commit increment rules

#### Scenario: First release

- **WHEN** no valid release tag exists
- **THEN** GitVersion calculates from the configured initial version

### Requirement: Release artifacts target an immutable commit

The release tag, packaged archive, and GitHub release SHALL all identify the exact `main` commit evaluated by the triggering workflow, even if `main` advances before publication completes.

#### Scenario: Main advances during publication

- **WHEN** another change reaches `main` after a release run has calculated its version
- **THEN** the earlier run's tag, archive, and GitHub release still target and contain the earlier evaluated commit

#### Scenario: Generated release contents

- **WHEN** a qualifying release is published
- **THEN** its title and tag use `v{major}.{minor}.{patch}`, its archive uses the calculated version, and its generated notes cover changes since the previous release

### Requirement: Release jobs use least privilege

The release workflow SHALL declare no permissions by default, SHALL grant only `contents: read` to jobs that inspect or package repository content, and SHALL grant `contents: write` only to the job that creates the tag and GitHub release.

#### Scenario: Calculation and packaging execute

- **WHEN** the calculation and packaging jobs run
- **THEN** neither job has `contents: write` or persisted Git checkout credentials

#### Scenario: Publishing executes

- **WHEN** the publishing job creates a release tag and GitHub release
- **THEN** only that job receives `contents: write` and it receives no unrelated write permission

#### Scenario: Workflow-wide permissions are inspected

- **WHEN** the release workflow permissions are reviewed
- **THEN** no workflow-wide `contents: write` grant exists

### Requirement: Concurrent and repeated runs are safe

The release system SHALL serialize publication decisions and SHALL refuse to move or overwrite an existing tag or replace an existing release asset.

#### Scenario: Two qualifying changes arrive close together

- **WHEN** multiple release evaluations overlap
- **THEN** publication is serialized and each calculation is revalidated against the release state before mutation

#### Scenario: Existing tag targets another commit

- **WHEN** the calculated tag already exists and targets a different commit
- **THEN** publication fails without moving the tag or creating a conflicting release

#### Scenario: Retry after partial publication

- **WHEN** the expected tag already targets the evaluated commit but the corresponding GitHub release does not exist
- **THEN** a retry can safely complete the missing release without recreating or moving the tag

#### Scenario: Release already exists

- **WHEN** both the expected tag and GitHub release already exist
- **THEN** the run completes without replacing release assets

### Requirement: Trusted release controls are documented

The repository SHALL document the automated release policy, required protected-branch and tag-ruleset settings, publishing environment controls, and recovery procedure without requiring long-lived personal credentials.

#### Scenario: Maintainer configures repository controls

- **WHEN** a maintainer prepares the repository for automated releases
- **THEN** the documentation identifies the trusted workflow actor, allowed tag pattern, environment configuration, and required least-privilege token settings

#### Scenario: Maintainer investigates a failed release

- **WHEN** tag or release publication fails after a qualifying change reaches `main`
- **THEN** the documentation explains how to inspect and safely retry the immutable release without manually calculating a replacement version

### Requirement: Release outputs are signed and attested

The release system SHALL create a GPG-signed annotated tag for the planned SHA, publish SHA-256 checksums and detached GPG signatures for the release archive and checksum manifest, and create GitHub build provenance for the archive. It SHALL fail closed when an existing expected tag does not verify with the configured release signing key.

#### Scenario: Qualifying release is published

- **WHEN** a qualifying release is published
- **THEN** its tag verifies with the release signing key, its archive and checksum manifest have detached signatures, and its archive has GitHub build provenance

#### Scenario: Existing tag cannot be verified

- **WHEN** the expected tag already exists but does not verify with the configured release signing key
- **THEN** publication fails without creating or replacing a release asset
