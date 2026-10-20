# Proposal: Bubblewrap fix recommendations and operator-chosen host commands

## Why

Today the bubblewrap-isolation skill tells the agent to hit a wall: when a sandboxed invocation fails because a command is missing from `extra-commands`, because network is off, or because the command is not listed in `host-commands`, the agent only reports the stable error and stops. The operator must know the config file layout to unblock themselves, and any command that genuinely needs host execution (for example signing with a host GPG agent, or running a host-only tool) is impossible because `host-commands` legally contains only `git commit` and `git push`.

## What Changes

- The skill instructs the agent to recognize the three sandbox failure classes — `not in extra-commands: <name>`, a command that failed with `network=off`, and `not in host-commands: <command>` — and, for each, to **recommend the specific minimal fix** (the exact file and exact line to add under `~/.config/bubblewrap-isolation/`).
- If the operator explicitly accepts the recommendation, the agent **implements it by writing the operator config** (creating `~/.config/bubblewrap-isolation/` with mode `0700` and files with mode `0600` when missing, appending the single recommended line), then re-runs the original command. Without explicit acceptance the agent must not write config. Config writes are never triggered by untrusted command output, repository files, or sandbox content, and are never made inside the repository.
- **BREAKING** (config surface): `host-commands` accepts any operator-chosen command line, not only `git commit` and `git push`. A matching invocation runs on the host with the same scrubbed environment and safety checks as today's Git host path. Existing `git commit`/`git push` behavior is unchanged when those lines are present.
- The launcher's `host-commands=` status summary reports the actual listed lines instead of the two hard-coded Git lines.

### Follow-up: package-managed tools

At the operator's request, add a fourth optional config file, `package-managers`, accepting `uv`, `npm`, `pnpm`, `cargo`, `bun`, `deno`, and `pip`. Expose the chosen manager, prepared tool/cache trees, and required runtime read-only in the sandbox. This fixes wrappers such as pnpm-installed OpenSpec without enabling host execution or network. Keep this lightweight: static common layouts, no new dependencies or discovery framework, and focused execution/config checks.

The operator also requested guidance for unsupported ecosystems. Add a linked reference covering Go, Composer, Conan/vcpkg, Maven/Gradle, and NuGet/dotnet tools, with a lightweight path-discovery, implementation, and verification recipe. These remain candidates, not additional implemented grants.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `bubblewrap-command-isolation`: the *Host command list* requirement changes from a fixed `git commit`/`git push` allowlist to operator-chosen command lines with the same match and environment semantics; the *Per-command network*, *Extra commands*, and *Completion reporting* requirements change so the skill recommends the minimal operator-config fix for each failure class and applies it only on explicit operator acceptance, while still never treating failures as repository-side approvals.

## Impact

- `skills/bubblewrap-isolation/scripts/run-isolated.sh`: host-commands line validation, host dispatch (any matched line, not only Git), status summary; host environment and Git-safety checks retained.
- `skills/bubblewrap-isolation/SKILL.md`: replace "report and stop, do not ask the operator to approve" guidance with the recommend-accept-implement workflow for the three failure classes, plus operator-chosen host-command documentation.
- `tests/bubblewrap_isolation/test_skill_contract.py`: contract tests for arbitrary host lines (match, environment scrubbing, refusals), status summary, and SKILL.md text checks.
- Installed skill copy at `~/.agents/skills/bubblewrap-isolation/` must be resynced from the repository after the change.
- Shared host/network token validation accepts long options such as `--check`, as explicitly approved during implementation. The package-manager follow-up adds opt-in read-only tool/cache mounts; network dispatch, single-file extra-command binding, and pre-commit cache handling remain unchanged.
