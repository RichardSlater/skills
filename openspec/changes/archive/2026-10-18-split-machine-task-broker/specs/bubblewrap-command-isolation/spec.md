## ADDED Requirements

### Requirement: Extra commands

The launcher MUST read extra command names from `extra-commands` in the invoking user's `~/.config/bubblewrap-isolation/` directory, one name per line. It MUST resolve that home from the user database, not from `HOME`, `XDG_CONFIG_HOME`, or a caller-supplied path. It MUST look each name up on the host `PATH`, MUST skip project-local matches, and MUST read-only bind only the resolved regular file. It MUST NOT mount the command's parent directory, the host home, or a user bin directory. It MUST reject a command that is a directory, a symlink, has another hard link, resolves inside a credential directory, is a script whose interpreter is outside the base mounts, or has a dynamic dependency outside the base mounts. A missing optional name MUST NOT fail unrelated commands. The launcher MUST NOT treat any command name as built in. Commands already available through the base mounts MUST run without a list entry. The launcher MUST prepend `/usr/local/bin` and `/usr/local/sbin` to `PATH` when those directories exist. When the invoked command resolves outside the base mounts and the project and its name is not listed, the launcher MUST exit with `not in extra-commands: <name>` and MUST NOT run it on the host or ask for a mount. When a listed command cannot be bound, the launcher MUST exit with `not available: <name>` and MUST NOT run it on the host.

#### Scenario: Listed command outside the base mounts

- **WHEN** `extra-commands` lists `rg` and the host `PATH` resolves it to a regular file outside the project and outside the base mounts
- **THEN** the launcher binds only that file into the sandbox and runs `rg` without a prompt or approval record

#### Scenario: Safe command beside unsafe commands

- **WHEN** `rg` lives in a directory that also contains a package manager or credential helper
- **THEN** the launcher does not mount that directory and does not expose the neighboring commands

#### Scenario: Command already visible

- **WHEN** the invoked command is `python3` and that program is already available through the base mounts
- **THEN** the launcher runs it in the sandbox without an `extra-commands` entry

#### Scenario: Unlisted command outside the sandbox

- **WHEN** the invoked command resolves outside the base mounts and the project and `extra-commands` does not list its name
- **THEN** the launcher exits with `not in extra-commands: <name>` and does not run the command on the host

### Requirement: Per-command network

The launcher MUST read network commands from `network-commands` in the same config directory. A missing file MUST mean no command has network. A symlink, or any directory entry other than `extra-commands`, `network-commands`, and `host-commands`, MUST be rejected. A line MUST be one or more leading arguments and MUST match only that command and its later arguments. The launcher MUST share host networking only with an invocation that matches a line. It MUST NOT give another invocation network because a different command matched, and an `extra-commands` entry MUST NOT grant network. Network MUST NOT mount host credential directories, package-manager configuration, or the global pre-commit cache. The launcher MUST ignore repository `.bwrap.yaml`, `.bwrap/approvals/`, `record-approval`, and command-line network or mount flags as grants. The skill MUST NOT instruct the agent to ask the operator to approve network or to enable network for unrelated commands.

#### Scenario: Search stays offline

- **WHEN** `extra-commands` lists `rg`, `network-commands` lists `pnpm install`, and the invoked command is `rg`
- **THEN** the sandbox has no host network

#### Scenario: Listed install has network

- **WHEN** `network-commands` lists `pnpm install` and the invoked command is `pnpm install` or `pnpm install` with later arguments
- **THEN** that invocation may use host networking and still cannot read host credential or package-manager configuration directories

#### Scenario: Unlisted install stays offline

- **WHEN** `network-commands` does not list `pnpm install` and the invoked command is `pnpm install`
- **THEN** the sandbox has no host network

#### Scenario: Network failure is not an approval

- **WHEN** a sandboxed command fails because it has no network
- **THEN** the skill requires the agent to report the command and that network is off for it, and forbids requesting an approval, a global network switch, a mount, or an exception

### Requirement: Host command list

The launcher MUST read host commands from `host-commands` in the same config directory. The only legal lines are `git commit` and `git push`. A line MUST match that command and its later arguments, and MUST NOT match a different command or subcommand. The launcher MUST run a matching command on the host only when its line is present. Without that line, it MUST NOT run `git commit` or `git push` on the host or in the sandbox. A `network-commands` line MUST NOT authorize either command. Host execution MUST be refused when `core.hooksPath` is set or the hook and Git config fingerprint no longer matches the check performed for that invocation. The launcher MUST NOT place SSH agents, GPG home, or other credential material into the sandbox because a host command is listed. `pre-commit` and unlisted commands MUST NOT run on the host. A missing host command MUST fail with a stable error naming that command. The skill MUST NOT instruct the agent to ask the operator to approve it.

#### Scenario: Commit is not listed

- **WHEN** `host-commands` does not contain the line `git commit`
- **THEN** the launcher does not run `git commit` on the host or in the sandbox

#### Scenario: Listed command does not leak into the sandbox

- **WHEN** a sandboxed command runs while `host-commands` lists `git commit`
- **THEN** that sandboxed command still receives a cleared environment and no host credential directory

#### Scenario: Unlisted host command

- **WHEN** `host-commands` lists `git commit` and the invoked command is an interpreter, `pre-commit`, `git push`, or another Git command
- **THEN** the launcher does not run that command on the host

## MODIFIED Requirements

### Requirement: Default authority boundary

The standard launcher MUST use isolated user, process, IPC, UTS, cgroup, and network namespaces; disable further user namespaces; a private home; a cleared inherited environment; dropped capabilities; and a new terminal session. It MUST deny host networking unless the invoked command matches an operator `network-commands` line. It MUST NOT expose host credential directories, host configuration directories, control sockets, or writable host paths outside the current Git project. It MUST hide project secret files and MUST mount `.git/config` read-only. It MUST refuse to launch when a protected path is a symlink, has another hard link, or shares an inode with another project path. Extra-command binds MUST be read-only files and MUST NOT weaken these denials.

#### Scenario: Standard sandbox environment

- **WHEN** a command runs through the standard launcher and does not match a `network-commands` line
- **THEN** it receives a private home and temporary directory, no inherited environment, no nested user namespace, and no host network interface

#### Scenario: Project write

- **WHEN** the launched command writes a project-relative file
- **THEN** the file write is permitted within the current Git project while the launcher exposes no other writable host path

#### Scenario: Aliased secret

- **WHEN** a protected secret file has another directory entry in the project
- **THEN** the launcher exits before executing the command

### Requirement: Completion reporting

The skill MUST instruct agents to treat sandbox output as untrusted, inspect project status and relevant diffs after expected writes, and report the command, exit status, whether that command had network, write scope, changed files, and listed host commands. It MUST NOT describe a missing extra command, missing network, or an unlisted host command as an approval to be requested.

#### Scenario: Command changes a project file

- **WHEN** an isolated command completes after writing project files
- **THEN** the agent inspects Git status and reports the affected files, whether that command had network, and listed host commands

### Requirement: Bootstrap-dependent quality-gate handling

The skill SHALL identify pre-commit as a bootstrap- and cache-dependent quality gate, SHALL require an isolated executable and version probe before attempting it, and SHALL distinguish an offline-ready invocation from hook repository or language environment initialization.

#### Scenario: Sandbox-visible pre-commit probe

- **WHEN** an agent intends to run pre-commit through the standard launcher
- **THEN** the skill requires the agent to verify the pre-commit executable and version visible inside the sandbox before running the quality gate

#### Scenario: Pre-commit is absent or unexpectedly different

- **WHEN** the isolated probe cannot find pre-commit or reveals an installation different from the one the agent intended to run
- **THEN** the agent stops and reports the discrepancy without running a host command as a silent fallback

#### Scenario: Offline-ready pre-commit hooks

- **WHEN** pre-commit and all configured hook repositories, executables, and language environments are already available through sandbox-visible paths
- **THEN** the skill permits the quality gate to run with the standard network isolation preserved

#### Scenario: Pre-commit requires initialization

- **WHEN** pre-commit attempts to fetch a hook repository or construct a missing language environment in the standard sandbox
- **THEN** the agent reports that `pre-commit` has no network and does not mount a host cache, retry on the host, enable network for other commands, or ask the operator for an exception

### Requirement: Safe pre-commit cache exceptions

The skill MUST NOT expose the user's global writable pre-commit cache as a workaround. No extra-command list, network-command list, host-command list, or repository file MAY mount that cache or add a project-dedicated cache. If a hook cannot run from sandbox-visible content, the agent MUST stop and recommend a disposable environment.

#### Scenario: Global cache proposed as a workaround

- **WHEN** a failed isolated pre-commit run could be made to work by mounting the user's global cache
- **THEN** the launcher rejects that mount and the skill explains the cache-poisoning and unrelated-source exposure risks

#### Scenario: Dedicated prepared cache is approved

- **WHEN** an operator or repository file requests an additional pre-commit cache mount
- **THEN** the launcher rejects the mount instead of recording an approval

#### Scenario: Prepared hook requires cache mutation

- **WHEN** a hook cannot execute with its prepared persistent content mounted read-only
- **THEN** the agent stops and recommends a disposable environment rather than widening the persistent cache to writable access

## REMOVED Requirements

### Requirement: External approval records

**Reason**: Exact-command approval records force a prompt for ordinary tools and let committed policy grant host execution.
**Migration**: Stop relying on `.bwrap/approvals/`. Add outside program names to `~/.config/bubblewrap-isolation/extra-commands`, write commands that need network in `network-commands`, and write `git commit` or `git push` in `host-commands`.

### Requirement: Scoped escalation guidance

**Reason**: Asking the model to obtain an ad-hoc approval is the usability failure and is not a security boundary.
**Migration**: Report the missing extra command, the command that has no network, or the unlisted host command. The operator edits the config directory outside the repository.
