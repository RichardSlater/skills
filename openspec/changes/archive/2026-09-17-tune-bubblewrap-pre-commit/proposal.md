## Why

The Bubblewrap skill currently treats `pre-commit` like an ordinary offline command even though it commonly needs a user-installed executable, a persistent hook cache, language environments, and network access during initialization. In the standard private-home, no-network sandbox this causes predictable failures or silently selects a different system installation, so the skill needs explicit compatibility checks and safe fallback guidance.

## What Changes

- Add pre-commit-specific guidance that distinguishes running fully prepared hooks from initializing hook repositories and language environments.
- Require agents to verify the executable and version visible inside the sandbox before attempting the quality gate.
- Define when isolated pre-commit execution is supported: local or vendored hooks, or a fully prepared dedicated cache exposed through an explicitly approved exception.
- Require agents to stop and report missing executables, network-dependent initialization, or missing environments rather than retrying or silently running outside the sandbox.
- Document safe alternatives and reject mounting the user's global writable pre-commit cache as a default workaround.
- Add validation coverage for the new guidance and launcher behavior where practical.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bubblewrap-command-isolation`: Extend safe invocation and scoped-escalation requirements for bootstrap- and cache-dependent tools, with explicit pre-commit behavior.

## Impact

- Affects `skills/bubblewrap-isolation/SKILL.md` and the Bubblewrap isolation specification.
- May add focused tests or validation fixtures for sandbox-visible tooling and offline pre-commit failure handling.
- Does not add network access, expose host credentials, or change the standard launcher's default authority boundary.
- Changes agent workflow by requiring a preflight decision before running `pre-commit` in the sandbox.
