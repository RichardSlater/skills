## 1. Operator files

- [x] 1.1 Read `extra-commands`, `network-commands`, and `host-commands` from the invoking user's real `~/.config/bubblewrap-isolation/`, rejecting symlinks, unknown files, unknown lines, and caller-supplied config paths.
- [x] 1.2 Stop treating `.bwrap.yaml`, `.bwrap/approvals/`, `--share-net`, `--mount`, and `record-approval` as grants.

## 2. Sandbox

- [x] 2.1 Look up each `extra-commands` name on the host `PATH`, skip the project, and bind that one read-only file with the closure checks from the design. Prepend `/usr/local/bin` and `/usr/local/sbin` to `PATH`.
- [x] 2.2 Exit `not in extra-commands: <name>` when the invoked command is outside the base mounts and project and is not listed. Exit `not available: <name>` when a listed command cannot be bound. Do not run either case on the host.
- [x] 2.3 Share host networking only when the invocation matches a `network-commands` line. Keep every other command offline, and keep credential directories, package-manager configuration, and the global pre-commit cache unmounted.

## 3. Host commands

- [x] 3.1 Run `git commit` on the host only when `host-commands` lists `git commit`, and `git push` only when it lists `git push`. Without that line, run the command neither on the host nor in the sandbox.
- [x] 3.2 Keep the hook and `core.hooksPath` refusal checks, reject unlisted host commands, and keep host credentials out of sandboxed commands.
- [x] 3.3 Keep `pre-commit` on the sandboxed path.

## 4. Skill contract and tests

- [x] 4.1 Rewrite the skill so a missing extra command, network line, or host command is a stable error, not an approval request. Completion reports name whether this command had network and which host commands are listed.
- [x] 4.2 Replace approval-record contract tests with extra-command lookup, per-command network, and host-command tests.
- [x] 4.3 Run the Bubblewrap contract tests and record any prerequisite failure without falling back to unsandboxed execution.
