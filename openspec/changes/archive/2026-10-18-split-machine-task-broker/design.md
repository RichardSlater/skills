## Context

The launcher currently grants extra authority from committed `.bwrap/approvals/` records. An ordinary tool such as `rg` needs a controlling terminal and a commit. Those tools often live beside package managers and credential helpers, so mounting their directory is the wrong fix.

The skill is still voluntary. This change does not add a Pi extension that forces every command through the launcher.

Using it:

```text
~/.config/bubblewrap-isolation/
  extra-commands   # program names to look up, one per line: "rg"
  network-commands # commands that get network, one per line: "pnpm install"
  host-commands    # optional lines: "git commit" and "git push"
```

- `python3` and `git` are already visible. They need no entry.
- `rg` is not visible, so the operator adds `rg`. The launcher looks up that name and binds that one file. `rg` still has no network.
- `pnpm install` gets network every time that line is present. If `pnpm` itself is outside the sandbox, `pnpm` also goes in `extra-commands`. The network line does not turn network on for `rg`.
- `git commit` in `host-commands` means that command. It is not a permission name.
- If a line is missing, the command fails and names the file. Do not ask for an approval.
- Nothing in the Git repository can add these permissions.

## Goals / Non-Goals

**Goals:**

- Run commands that are already visible without a prompt.
- Make an outside program available by listing its name and looking it up.
- Give network only to the command that needs it.
- Make host execution a list of real commands.
- Keep credentials out of the sandbox.
- Ignore the repository as a source of extra authority.

**Non-Goals:**

- A hidden built-in list of tools.
- A global network switch.
- A harness that forces every tool through the launcher.
- Per-command approval prompts.
- Guessing that an unlisted command needs network.
- A capabilities vocabulary, repository policy, extra mounts, devices, or D-Bus.
- Running `gpg` or `pre-commit` on the host.
- Mounting a directory because one safe command lives there.

## Decisions

### Three lists of commands

The config directory is `~/.config/bubblewrap-isolation/` in the real home of the user running the launcher. Resolve that home from the user database. Ignore `HOME`, `XDG_CONFIG_HOME`, and any caller-supplied path. The directory may contain only `extra-commands`, `network-commands`, and `host-commands`. Any other entry is an error. Each present file must be a regular file and must not be a symlink. A missing file means that list is empty.

`extra-commands` is one program name per line, such as `rg`. The launcher looks the name up on the host `PATH`, skips the project, and read-only binds that one file. There is no built-in list. A command already inside the base mounts needs no line. `/usr/local/bin` and `/usr/local/sbin` are on `PATH` because `/usr` is already mounted.

`network-commands` contains the command, one per line. A line is one or more leading arguments, such as `curl` or `pnpm install`. It matches that command and its later arguments. It does not match a different command: `pnpm install` does not give network to `pnpm publish` or `rg`.

There is no ambient network. Each launcher invocation decides from its own argv. Listing a program in `extra-commands` does not give it network.

`host-commands` uses the same leading-arguments format. The only legal lines are `git commit` and `git push`. Those commands run on the host, so they are not also network-commands. `git push` either runs on the host or it does not run.

These files stay as written until the operator edits them. They are not per-command prompts.

Alternative considered: a `tools` file, or built-in `rg` and `fd`. Rejected. The operator should see the same kind of list as the other files: command names, one per line, looked up on `PATH`.

Alternative considered: an empty `network` file that turns network on for every command. Rejected. `rg` would gain network it does not need.

Alternative considered: built-in knowledge that `pnpm install` always has network. Rejected. The model could choose that command to obtain network. The operator lists it once; after that, that command always has network.

### Lookup binds one file

For each listed name, resolve the host `PATH`, skip the project, and read-only bind that one regular file. Never mount its parent directory, the host home, or a user bin directory.

Refuse the bind when the path is a directory, a symlink, an extra hard link, or inside a credential directory. Also refuse a script whose interpreter is outside the base mounts, and an ELF whose libraries are outside the base mounts.

If the invoked command is outside the base mounts and the project, and its name is not listed, exit `not in extra-commands: <name>` and do not run it on the host. If it is listed but cannot be bound, exit `not available: <name>`. A missing extra command does not fail unrelated commands.

### Host commands stay separate from network

A listed host command runs on the host. `git commit` and `git push` run neither on the host nor in the sandbox unless their line is present. The existing `core.hooksPath` and hook fingerprint checks stay. Other Git commands remain sandboxed and offline unless their own `network-commands` line matches. `pre-commit` stays sandboxed. Listing a host command does not copy SSH or GPG material into the sandbox. `git commit` can sign because it runs on the host, not because `gpg` is exposed.

Network does not mount `~/.npmrc`, `~/.cargo`, credential directories, or the global pre-commit cache. A networked `pnpm install` still cannot read those files.

`--share-net`, `--mount`, `.bwrap.yaml`, and `.bwrap/approvals/` do not grant authority. `record-approval` does not record anything; it exits and points at the config directory.

## Risks / Trade-offs

- [Caller can skip the launcher] → Document that only a harness makes this a boundary. The launcher still refuses project-supplied grants.
- [`rg` is absent until listed] → The error names `extra-commands`. Do not fall back to a host or a directory mount.
- [A broad line such as `pnpm` gives network to every pnpm subcommand] → The network line is the leading arguments. Document that `pnpm install` is the useful line, not `pnpm`.
- [`pnpm install` is offline until listed] → Print `network=off` and the command. The skill names the missing line and does not suggest a global switch.
- [`/usr/local/bin` exposes local binaries such as `docker`] → Do not mount their sockets. This is not permission to use a container runtime.
- [The operator config is trusted] → It is outside the project and cannot be a symlink. A listed host `rg` is operator trust, not project trust.
- [Old approval records stop working] → Ignore them. The config directory replaces them.

## Migration Plan

1. Ignore approval records and mount flags as grants.
2. Look up and bind names from `extra-commands`.
3. Grant network only when the invocation matches a `network-commands` line.
4. Honor the `git commit` and `git push` host-command lines.
5. Update the skill so a missing extra command, network line, or host command is an error, not a question.
6. Replace approval contract tests.

Rollback is reverting the launcher and skill together. The launcher does not delete old approval directories.

## Open Questions

None.
