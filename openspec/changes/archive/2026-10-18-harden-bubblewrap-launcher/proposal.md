## Why

The Bubblewrap skill had replaced its launcher with a copy-paste template and an in-project approval file. That file could be rewritten through a second hard link, and host prefixes could authorize arbitrary executables.

## What Changes

- Restore a fail-closed launcher as the only invocation path.
- Store shared approvals in committed `.bwrap/approvals/` and ignore repository `.bwrap.yaml` plus uncommitted edits.
- Reject symlinks, hard links, and inode aliases before launch.
- Allow host execution only for `git commit`, `git push`, and `pre-commit`, blocked when hook fingerprints change.
- Disable nested user namespaces and cover the regression with launcher tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bubblewrap-command-isolation`: launcher enforcement, external approvals, and host allowlist.

## Impact

`skills/bubblewrap-isolation`, its contract tests, and the live Bubblewrap spec.
