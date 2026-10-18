## Why

The fail-closed launcher still lets a listed `git commit` or `git push` inherit `GIT_DIR`, `GIT_SSH_COMMAND`, and other Git environment overrides, so host execution can leave the project hooks that were checked. A Git root that contains the operator's home, or a secret file below the project root, is still writable or readable inside the sandbox. Those gaps make the boundary look stricter than it is.

## What Changes

- **BREAKING**: Listed `git commit` and `git push` run with a cleaned environment. The launcher forwards only a project-scrubbed `PATH`, the real `HOME`, `USER`, and, for `git push` only, an existing `SSH_AUTH_SOCK`. Identity and signing come from the real home, not from inherited Git or GnuPG variables.
- **BREAKING**: Refuse to launch when the Git project root is the invoking user's home or an ancestor of that home, or when the project contains a credential directory such as `.ssh` or `.config/bubblewrap-isolation`. Do not mask those directories.
- **BREAKING**: Refuse to launch when `~/.config/bubblewrap-isolation` or one of its three list files is writable by group or other.
- Hide `.env`, `.env.*`, and `.envrc` anywhere in the project, not only at the root.
- Fail closed when the hardlink scan or ELF dynamic-section parse cannot be completed. Do not treat missing `readelf` output as a safe closure.
- Copy DNS files for a network command only after resolving them. Refuse a target under the home directory or another credential path. A content copy of a system resolver stub remains allowed so per-command network still resolves names.
- Describe operator `network-commands` in the skill description. The description must not say that network is always off.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `bubblewrap-command-isolation`: Tighten host-command environment, project credential exposure, secret masking, config permissions, extra-command closure checks, and network file copies. Correct the skill's network description.

## Impact

`skills/bubblewrap-isolation/scripts/run-isolated.sh`, `skills/bubblewrap-isolation/SKILL.md`, `tests/bubblewrap_isolation`, and `openspec/specs/bubblewrap-command-isolation`. Dotfiles repositories whose Git root is the home directory, and repositories that contain a credential directory, can no longer use this launcher. Group-writable operator config stops working until the operator tightens the mode. Extra commands whose dynamic section cannot be parsed become `not available`. Sandboxed commands can no longer read nested env files.
