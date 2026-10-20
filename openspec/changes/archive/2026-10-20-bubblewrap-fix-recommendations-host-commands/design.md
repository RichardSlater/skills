# Design: Bubblewrap fix recommendations and operator-chosen host commands

## Context

`skills/bubblewrap-isolation` ships a fail-closed Bash launcher (`scripts/run-isolated.sh`) plus a SKILL.md that governs how an agent uses it. The launcher reads three operator files from the invoking user's real `~/.config/bubblewrap-isolation/` (`extra-commands`, `network-commands`, `host-commands`) and grants nothing from the repository. Three failure classes exist today:

- `not in extra-commands: <name>` — invoked program is outside the base mounts and not listed.
- A sandboxed command exits non-zero with `network=off` on the status line — the command needed network that the invocation does not have.
- `not in host-commands: git commit` / `git push` — a Git host-bound command is not listed; it runs nowhere.

The current SKILL.md treats all three as terminal: report the stable error and stop, never ask the operator to approve anything. Operators who do not know the config layout are stuck, and `host-commands` is hard-wired to `git commit` and `git push` in three places in the launcher (line validation, dispatch guard, status summary), which blocks any legitimate host-only workflow (e.g., GPG signing via a host agent, a host-installed linter).

## Goals / Non-Goals

**Goals:**

- For each of the three failure classes, the skill instructs the agent to recommend the exact minimal operator-config fix (file + single line).
- On explicit operator acceptance, the agent implements the fix by writing to `~/.config/bubblewrap-isolation/` and re-runs the original command.
- `host-commands` accepts operator-chosen command lines; a matching invocation runs on the host with the same scrubbed environment and safety checks as today's Git host path.
- Existing `git commit` / `git push` behavior is unchanged when those lines are present.

**Non-Goals:**

- No new launcher subcommand for editing config (see D1).
- No repository-side approvals, no `--host`/`--share-net`-style request flags, no change to sandbox network or extra-command binding logic. The operator-requested package-manager follow-up adds only its explicit read-only runtime mounts.
- No interactive/long-running host sessions, no `sudo`/SSH workflows (already out of scope for the skill).

## Decisions

### D1: The agent edits operator config directly on acceptance; the launcher stays a pure consumer

The launcher keeps its current contract: it never creates or modifies the config directory. The fix is implemented by the agent (the trusted side of the boundary) using ordinary file writes, per SKILL.md instructions.

- *Alternative considered:* a launcher subcommand such as `run-isolated.sh add-config extra-commands rg`. Rejected: any process that can invoke the launcher could then self-serve permission widening, inverting the "only the operator grants" model. It also conflicts with the launcher's existing "MUST NOT create or change the mode of that directory" contract.
- Acceptance must be explicit operator consent for the specific recommendation. SKILL.md must state that config writes are never motivated by sandbox output, command output, repository files, or package metadata (all untrusted data), and never write anything inside the repository.

Config write rules the agent follows (documented in SKILL.md):

- Create `~/.config/bubblewrap-isolation/` with mode `0700` and each file with mode `0600` only when missing; never change the mode or ownership of an existing entry (the launcher refuses group/other-writable entries).
- Append exactly the one recommended line; never modify or delete other lines; refuse to proceed if the target file contains lines the launcher would reject (surface that error instead of "repairing" it).
- Never create symlinks; verify the final file is a regular file owned by the invoking user before re-running.
- After the write, re-run the original command through the launcher and report the status line.

### D2: Unified host-command matching, with `git commit`/`git push` remaining host-bound

Dispatch rule in `run_command`:

1. If the argv matches a `host-commands` line (existing prefix match, `argv_matches_line`) → run on the host. Now for **any** listed command, not only Git.
2. Otherwise, if the argv is `git commit` or `git push` → die `not in host-commands: git <sub>` (unchanged; these commands never run sandboxed).
3. Otherwise → the existing sandbox path (network line, extra-command binding).

Consequences:

- A listed command such as `pre-commit`-like tool or a host linter runs on the host when its prefix matches.
- A listed line `git` would match every `git` subcommand on the host — legal, operator-chosen, and documented as the operator's authority; nothing extra to code.
- The `not in host-commands` stable error remains available for the Git host-bound commands; for other commands the agent recognizes the "not on host" situation from the `execution=sandbox` status line when host execution was the intent, and recommends the line.

*Alternative considered:* an explicit `--host` request flag. Rejected: flags on the launcher are already defined as non-grants, and prefix matching already makes the grant precise per line.

### D3: Host-line validation and a refusal list

- Lines are validated like `network-commands` lines (`validate_network_line`/`valid_arg_token`): one or more leading-argument tokens, no slashes, no embedded whitespace. The shared validator accepts single- and double-hyphen options (`-q`, `--check`), but not a bare `--`. This narrowly expands network token validation too, explicitly approved during implementation because the existing validator rejected the required `some-tool --check` example. Network matching and dispatch remain unchanged. Unknown lines remain `unknown line in host-commands: <line>`.
- Lines whose first token is `bwrap`, `sudo`, `su`, `unshare`, `chroot`, or `pre-commit` are refused at parse time with the same stable error. Rationale: the first four can create their own namespaces/privilege contexts and bypass the sandbox entirely; `pre-commit` must remain a sandboxed quality gate (its cache and hook-repo model is built around the sandbox path, and host execution would read the global writable cache).
- This is a refusal *list* in the launcher, not a configurable allowlist — the operator cannot disable it.

### D4: Host environment and safety checks apply to every host command

The existing host path already builds the right environment (`env -i` with project-scrubbed `PATH`, real `HOME`, `USER`, and `SSH_AUTH_SOCK` only for `git push`). For arbitrary commands:

- The executable is resolved with the existing `resolve_host_executable` (host `PATH` lookup, project directories skipped, symlinked or project-resolved executables refused). Since validated lines contain no slashes, `argv[0]` is always a bare program name.
- `validate_host_metadata` and the two-phase hooks/config fingerprint check still run for every host invocation, Git or not. They are cheap, and the invariant "the project's Git metadata and hooks were reviewed and did not change during this invocation" is worth keeping for any host execution in the tree.
- `prepare_host_environment` keeps forwarding `SSH_AUTH_SOCK` only for `git push`.

### D5: Status summary reports actual lines

`host_commands_summary` prints the unique listed lines (comma-joined, in file order) instead of the two hard-coded Git lines. The status line format `host-commands=<summary>` is unchanged.

### D6: SKILL.md workflow for the three failure classes

Replace the current "report and stop, do not ask the operator to approve" guidance with a uniform loop, per failure class:

| Failure | Evidence | Recommended fix |
|---|---|---|
| Missing extra command | launcher exits `not in extra-commands: <name>` | add `<name>` to `extra-commands` |
| Network off | command failed, status line says `network=off`, failure is network-related | add the exact command prefix of the failed invocation to `network-commands` |
| Not on host | launcher exits `not in host-commands: <command>`, or host execution was intended but the status line says `execution=sandbox` for a command the operator wants on the host | add the exact command prefix line to `host-commands` |

For each: the agent states the file path (`~/.config/bubblewrap-isolation/<file>`), the exact line, and what the grant does and does not cover (that one command prefix only; no other command gains network/mount/host execution; no secrets mounted). It asks the operator to accept. Accept → implement per D1 and re-run. Decline or no answer → stop and report the stable error as today. `not available: <name>` is **not** in the table: the list entry exists but the program cannot be safely bound; the fix is host-side (install/repair the program), never a config edit, and the agent says so.

### D7: Optional package-manager tool trees

The operator requested lightweight support for globally installed `uv`, `npm`, and `pnpm` tools after a pnpm OpenSpec wrapper failed because its JavaScript tree was absent. Add `package-managers` to the existing private operator-config parser; one supported manager name per line (`uv`, `npm`, `pnpm`, `cargo`, `bun`, `deno`, `pip`), absent means no extra mounts. Reuse sandbox execution, network matching, and private HOME.

Use static common layouts: uv tools/Python/cache, pnpm home/cache, npm's active CLI-derived prefix (including NVM), `.npm-global`, and npm's `_cacache`. Bind these directories read-only, expose the selected manager and required Node executable, and add their bins to sandbox PATH. Preserve symlinks inside mounted package trees rather than binding over npm's symlink. Skip absent optional directories; reject unknown manager names and symlinked root paths. No host manager discovery commands, new dependencies, custom-path configuration, writable cache support, or automatic installation.

The operator subsequently requested Cargo, Bun, Deno, and pip using the same mechanism. Add Cargo bin/registry/git and rustup toolchains plus the single toolchain-selection settings file; Bun bin/global/cache; Deno bin and Linux cache; and pip user-site packages/cache. Pip console/GUI entry points are read from `.dist-info/entry_points.txt` with awk (no host imports), binding only the named user-bin scripts and the host Python runtime. Preserve private HOME, omit Cargo credential/config files, and set each manager's default storage environment variables. Arbitrary virtualenvs, custom Python layouts, and metadata-less pip scripts remain unsupported. Extend the existing table-driven fixture check rather than adding a testing framework. Real Deno execution cannot be verified where Deno is absent.

Enabling a manager exposes every installed tool and cached file in its trees, not just one command. Explain that scope before accepting a grant. Leave `.npmrc`, credential directories, global pre-commit cache, host execution, and network grants unchanged. Shared caches are read-only; operations needing cache/lock writes or downloads are outside the supported prepared-tool execution path.

Verify with focused fixture tests and actual installed manager version probes plus pnpm OpenSpec `list --json`, using temporary operator config in a test namespace rather than modifying the real operator config.

### D8: Unsupported-manager integration reference

Keep ecosystem-specific investigation guidance in `references/package-manager-integration.md`, linked from SKILL.md when an unsupported manager is encountered. Distinguish candidates from implemented config names. Start with existing project-local/single-file capabilities, map runtime and package data from authoritative docs, extend the existing parser/preparation case only when needed, and verify a real prepared tool rather than only a version probe. Explicitly address lock/cache writes without granting writable host caches. This documentation does not add runtime support for the candidate ecosystems.

## Risks / Trade-offs

- [Prompt injection induces the agent to widen config] → SKILL.md mandates that recommendations originate only from the operator's own request and the launcher's stable errors; command/sandbox output is untrusted data and never a trigger for a config write; each accepted write appends exactly one line for the one failing command.
- [Operator lists a dangerous host command] → D3 refusal list for namespace/privilege breakouts and `pre-commit`; the remaining surface is the operator's own authority, stated in SKILL.md.
- [Agent writes malformed config and breaks the launcher for all commands] → the launcher's existing validation (unknown entries/lines, symlinks, ownership, group/other-writable) fails closed with a stable error; SKILL.md requires the agent to re-run a canary (`-- true`) after writing and to surface any rejection instead of editing further.
- [Existing configs break] → they do not: `git commit`/`git push` lines validate under the new token rules and dispatch identically; stricter old installed copies keep refusing anything else (fail-closed direction) until resync.
- [Host `git` subcommand coverage grows (a `git` line matches all git commands)] → documented as operator-chosen authority; no code path changes beyond the existing prefix match.

## Migration Plan

1. Update `run-isolated.sh`, `SKILL.md`, and `openspec/specs` per the delta spec; run `tests/bubblewrap_isolation/test_skill_contract.py`.
2. Resync the installed copy `~/.agents/skills/bubblewrap-isolation/` from the repository so live agent sessions pick up the new launcher and skill text.
3. Operator configs need no migration. Rollback = revert the repository and resync the installed copy; no on-disk state is changed by this feature until an operator accepts a fix.

## Open Questions

(none)
