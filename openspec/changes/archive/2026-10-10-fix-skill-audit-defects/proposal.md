## Why

The repository-wide skill audit found unsafe credential handling, path traversal, uncancellable work, incomplete detection and validation, and misleading workflow documentation. Correct these defects without expanding repository mutation authority.

## What Changes

- Harden subprocess deadlines, container cleanup, filesystem access and consent gates.
- Correct workflow analysis, effective permissions, risk classification and provenance.
- Integrate approval/output guards and content-based assessment snapshots.
- Lock dependencies by hashes and correct skill documentation and local OpenSpec integration.
- Add offline regression coverage and validate all skills before signed publication.

## Capabilities

### New Capabilities

- `skill-audit-safety`: fail-closed skill execution and evidence handling.

### Modified Capabilities

None.

## Impact

Public skill helpers, documentation, tests and validation CI. Existing operator-authored skills are preserved and included. Ignored `.pi` instructions are corrected locally only by operator decision.
