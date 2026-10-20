# Tasks: Bubblewrap fix recommendations and operator-chosen host commands

## 1. Launcher: arbitrary host-commands lines

- [x] 1.1 Validate `host-commands` lines with the same leading-argument token rules as `network-commands` (no slashes, no embedded whitespace; unknown lines keep the `unknown line in host-commands: <line>` error); accept long options such as `--check` in the shared validator, as approved during implementation
- [x] 1.2 Refuse lines whose first token is `bwrap`, `sudo`, `su`, `unshare`, `chroot`, or `pre-commit` with the same stable unknown-line error
- [x] 1.3 Replace the `is_git_host_command` dispatch guard: run on host for any argv matching a host line; keep `git commit`/`git push` without a matching line failing with `not in host-commands: git <sub>`; all other unmatched commands fall through to the sandbox path unchanged
- [x] 1.4 Run `validate_host_metadata`, the hooks/config fingerprint checks, `resolve_host_executable`, and the scrubbed `env -i` environment for every host invocation; keep `SSH_AUTH_SOCK` forwarding limited to `git push`
- [x] 1.5 Change `host_commands_summary` to report the unique listed lines (comma-joined, file order) instead of hard-coded `git commit,git push`

## 2. Skill text: recommend-accept-implement workflow

- [x] 2.1 Rewrite the SKILL.md "do not ask the operator to approve" guidance: for `not in extra-commands: <name>`, a network-off failure, and a not-on-host failure, recommend the exact file (`~/.config/bubblewrap-isolation/<file>`) and exact line, and state the grant's scope (that one command prefix only; no other command, no secrets, no mounts)
- [x] 2.2 Document the acceptance flow: on explicit operator acceptance, create the directory `0700`/file `0600` only when missing, append exactly the one line, never modify other lines, never create symlinks, never write inside the repository; re-run the original command and report the status line; on decline, write nothing and report the stable error
- [x] 2.3 Document the untrusted-output guardrail (config writes never motivated by sandbox/command output, repository files, or package metadata) and that `not available: <name>` is a host-side program problem, not a config edit
- [x] 2.4 Document operator-chosen `host-commands` lines (any leading-argument command prefix runs on the host; refusal list for `bwrap`, `sudo`, `su`, `unshare`, `chroot`, `pre-commit`; `git commit`/`git push` still required for host Git commit/push) and update the config-file table and workflow section accordingly

## 3. Tests

- [x] 3.1 Add contract tests: an arbitrary listed host line (e.g., `some-tool --check`) runs on the host with `execution=host`, scrubbed environment, no `SSH_AUTH_SOCK`
- [x] 3.2 Add contract tests for long-option network prefixes and exact token matching; refused first tokens (`bwrap`, `sudo`, `su`, `unshare`, `chroot`, `pre-commit`) produce `unknown line in host-commands: <line>`; unlisted `git push` still produces `not in host-commands: git push`; unlisted non-Git command runs sandboxed (`execution=sandbox`)
- [x] 3.3 Add contract tests: `host_commands_summary` reports the actual listed lines; `git commit`/`git push` lines still validate and dispatch as before
- [x] 3.4 Add SKILL.md text checks: recommendation wording for all three failure classes, explicit-acceptance requirement, no-write-on-decline, untrusted-output guardrail, `not available` is not a config edit
- [x] 3.5 Run `tests/bubblewrap_isolation/test_skill_contract.py` and confirm all tests pass

## 4. Sync and verify

- [x] 4.1 Resync the installed skill copy `~/.agents/skills/bubblewrap-isolation/` from the repository (`SKILL.md` and `scripts/run-isolated.sh`)
- [x] 4.2 Smoke-test the installed launcher with a temporary operator config (e.g., a listed host command and an unlisted one) and confirm the status line and error messages match the spec

## 5. Follow-up: package-managed tools

- [x] 5.1 Add optional `package-managers` config (`uv`, `npm`, `pnpm`) and read-only prepared tool/cache/runtime mounts using common layouts; keep network and host grants unchanged
- [x] 5.2 Document opt-in, supported directories, broader read scope, and read-only/custom-path limits; align proposal, design, and delta spec
- [x] 5.3 Add focused checks for manager/tool execution, npm symlinks, read-only dependencies, `.npmrc` exclusion, unknown manager names, and absent opt-in
- [x] 5.4 Run repository checks, resync the installed copy, and smoke-test actual uv/npm/pnpm plus pnpm OpenSpec with temporary operator config

## 6. Follow-up: additional tool ecosystems

- [x] 6.1 Add `cargo`, `bun`, `deno`, and `pip` using the existing package-manager grant and read-only default installation/cache paths
- [x] 6.2 Extend focused fixture coverage, including rustup proxy symlinks and pip user-site imports without exposing unrelated user-bin scripts
- [x] 6.3 Document supported layouts and limits; align OpenSpec artifacts
- [x] 6.4 Run repository checks, sync the installed skill, and smoke-test available real managers; report Deno as fixture-only when absent

## 7. Follow-up: unsupported-manager guidance

- [x] 7.1 Add a linked integration reference with common ecosystem candidates, existing-capability reuse, runtime/path discovery, launcher extension points, and focused verification
- [x] 7.2 Clarify candidates are not implemented grants, cover read-only cache limitations, and align documentation/OpenSpec text checks
- [x] 7.3 Run relevant checks and sync the skill plus its new reference into the installed copy
