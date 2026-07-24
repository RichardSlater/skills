## Why

Publishing a release currently requires a maintainer to calculate a version, create a tag, and manually provide that tag to the release workflow even though the repository already uses GitVersion and Conventional Commits. Automating the decision and publication when qualifying changes reach protected `main` removes duplicated manual work while preserving the repository's release security controls.

## What Changes

- Evaluate Conventional Commits reaching `main` and apply the standard SemVer mapping: `fix` produces a patch, `feat` produces a minor, and `!` or a `BREAKING CHANGE:` footer produces a major release.
- Treat all other valid Conventional Commit types as non-releasing unless they declare a breaking change; a push with no release signal completes without creating a tag or release.
- Use GitVersion to calculate the next version from repository history and existing release tags.
- Automatically create a protected `v{major}.{minor}.{patch}` tag and GitHub release for the exact qualifying commit on `main`, with packaged assets and generated release notes.
- Validate the Conventional Commit input used for release determination so versioning behavior is predictable.
- Apply least privilege to GitHub Actions: default to no permissions, keep calculation and packaging read-only, and grant `contents: write` only to the job that creates the tag and release.
- Preserve release integrity through immutable commit targeting, concurrency control, duplicate checks, pinned actions, and documented repository ruleset requirements.
- Replace the existing manual tag-input release documentation with the automated release contract and failure/recovery guidance.

## Capabilities

### New Capabilities
- `automated-conventional-releases`: Determines SemVer releases from Conventional Commits on `main` and securely creates the corresponding tag, packaged asset, release notes, and GitHub release.

### Modified Capabilities

None.

## Impact

- Affects `GitVersion.yml`, `.github/workflows/release.yml`, Conventional Commit validation in GitHub Actions, and release documentation such as `README.md` and `CHANGELOG.md`.
- Changes the release trigger from a maintainer-supplied tag to qualifying changes reaching protected `main`.
- Requires GitHub repository rulesets and the `release` environment to permit only the trusted publishing job to create matching release tags and releases.
- Does not change application or skill APIs, but changes repository release operations and maintainer workflow.
