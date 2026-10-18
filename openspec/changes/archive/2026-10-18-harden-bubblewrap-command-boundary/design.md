## Context

The launcher already takes extra commands, network, and host execution only from `~/.config/bubblewrap-isolation/`. Sandboxed commands get `--clearenv`. Listed `git commit` and `git push` do not. They inherit `GIT_DIR`, `GIT_SSH_COMMAND`, `GIT_CONFIG_COUNT`, and the rest of the agent environment, then treat a stable hook fingerprint as proof that the project hooks were the ones checked.

The writable project bind is also larger than the credential denials. Those denials apply to extra-command files, not to the project itself. A repository whose root is the home directory, or that contains `.ssh` or the operator config, can change the next launch. Secret masking covers only the top-level `.env` names. The hardlink scan and ELF closure check both succeed when their tools produce no output.

## Goals / Non-Goals

**Goals:**

- Make a listed host Git command execute only the resolved `git`, against the project that was checked, with no inherited Git execution override.
- Keep ordinary sandboxed commands working, including per-command network name resolution through a system resolver stub.
- Fail closed when a scan or parse the boundary depends on cannot be completed.
- Keep the operator config as the only authority, and keep it from being group-writable.

**Non-Goals:**

- Installing or updating the copy under `~/.agents` or `~/.pi`.
- A global network switch, a host `pre-commit` fallback, prompts, or repository approvals.
- Seccomp, resource limits beyond the existing `/tmp` cap, or a VM boundary.
- Reviewing the contents of repository hooks. A listed host command may still run project hooks whose fingerprint matched that invocation.
- A second environment language for locale, author, date, `GNUPGHOME`, or `GPG_TTY`. Commit identity and signing come from `~/.gitconfig` and `~/.gnupg` through the real `HOME`.
- A mount policy for credential directories inside a project. Presence is a launch refusal, not a tmpfs overlay.
- Classifying every Git config origin. Repository-local `core.sshCommand` is one `git config --local` check.
- Hiding every possible secret filename. Nested masking covers `.env`, `.env.*`, and `.envrc` only.

## Decisions

### 1. Host Git starts from an empty environment

`run_host` will `exec` the resolved Git binary with an environment constructed by the launcher, not the inherited environment. The absolute Git path is still resolved outside the project.

Forward only:

- `PATH`, with every project entry removed;
- `HOME` set to the real home from the user database;
- `USER` from that same database record;
- `SSH_AUTH_SOCK` only for a listed `git push`, and only when it is an existing socket with no symlink component.

Do not forward any other variable. That includes every `GIT_*` variable, `GNUPGHOME`, `GPG_TTY`, and locale variables. `HOME` is enough for `~/.gitconfig` and `~/.gnupg`.

Alternative considered: unset only the known dangerous names and keep the rest. That misses the next Git variable and still leaks agent tokens into hooks. A short allowlist is the smaller authority. A longer allowlist for author variables and signing paths was rejected because it adds parsers without closing a hole the empty environment leaves open.

### 2. Re-check the project, not every config origin

After constructing the environment, and before `exec`, run the existing hook fingerprint and `core.hooksPath` checks with that environment. Also refuse host execution when `git config --local --get core.sshCommand` succeeds. A global or system `core.sshCommand` is left alone because it is not in the repository and the inherited environment can no longer supply one.

Alternative considered: parse `git config --show-origin` and allow or refuse each origin. That is a second policy language for a check `--local` already expresses.

### 3. Refuse a project that contains the home or a credential directory

If the canonical project root is the real home, or is an ancestor of it, exit before launching. Masking those directories would still leave the rest of the home writable.

If any other project contains `.ssh`, `.gnupg`, `.aws`, `.kube`, `.docker`, `.config/git`, `.config/gh`, `.cache/pre-commit`, or `.config/bubblewrap-isolation`, exit before launching. Do not add a tmpfs mount for those paths. A repository that needs one of those directories is outside this launcher.

### 4. Extend env masking to every depth

During the existing project walk, protect a file or directory whose final component is `.env`, `.envrc`, or matches `.env.*`. This includes `.env.example`, because the current top-level rule already hides `.env.*`. A symlink with one of those names refuses launch. Do not add a new walk.

### 5. Tool failures are launch failures

Run the inode walk so its exit status is visible. A non-zero `find`, including a permission error, refuses launch. Do not build the alias map from a partial listing.

For an extra-command ELF, missing `readelf`, a non-zero `readelf` status, or empty dynamic output is `not available`. A static ELF is acceptable only when `readelf` reports that there is no dynamic section. Do not add a separate trust check for the `readelf` binary itself.

### 6. Copy resolver content, do not mount the target

For a network invocation, canonicalize `/etc/resolv.conf` and `/etc/hosts`. Refuse a canonical path under the real home, under a credential directory, or outside `/etc` and `/run`. Otherwise open the canonical file and copy its content with `--ro-bind-data` onto the sandbox path. That keeps systemd's `/run/systemd/resolve/stub-resolv.conf` usable without mounting `/run` or following a symlink into the home directory.

Certificate directories are bound only when the directory itself is not a symlink and its canonical path stays under `/etc`. A home or credential target refuses the launch.

### 7. Operator config must be a private directory

When the config directory exists, it and each present list file must be owned by the invoking uid and must not be writable by group or other. A missing directory remains an empty configuration. Do not create or chmod the directory from the launcher.

### 8. Say when network is on

The skill description will state that network stays off unless the invoked command matches an operator `network-commands` line. It will not say that the sandbox unconditionally has no network.

## Risks / Trade-offs

- [Cleaned host Git drops agent-set author variables and custom `GIT_CONFIG_GLOBAL`] → Identity comes from `~/.gitconfig` through the real `HOME`. Operators who need another config path put it there, not in the launcher environment.
- [A custom `GNUPGHOME` or `GPG_TTY` is not forwarded] → Signing uses the default `~/.gnupg` from `HOME`. An unusual signing setup runs outside this launcher.
- [Global `core.sshCommand` still runs on host push] → It is the operator's own config. Repository-local and inherited values are refused.
- [Repository hooks still run on listed host commands] → Accepted. The fingerprint check remains, and this change stops that check from being pointed at a different `GIT_DIR`.
- [Nested `.env.example` becomes unreadable in the sandbox] → Same name rule as the project root.
- [A project containing an intentional `.ssh` fixture cannot use the launcher] → Refusal is simpler than a credential mount policy.
- [DNS stubs outside `/etc` and `/run` fail network commands] → Report the path. Do not mount the parent to make resolution work.

## Migration Plan

No repository file changes are required. Operators with a group-writable config directory remove group and other write bits. A home-directory Git root, or a repository that contains a credential directory, cannot use this launcher. Roll back by reverting the launcher and skill together so the spec and the script do not diverge.

## Open Questions

None. The short host environment and the launch refusals are the intended breaks.
