# bubblewrap-command-isolation Specification

## Purpose

Define safe-by-default Bubblewrap execution for short-lived agent-run commands in the current Git project.

## Requirements

### Requirement: Standard isolated invocation

The skill SHALL provide a launcher for a command argument array run from inside a Git working tree. The launcher MUST require Bubblewrap and a user namespace, MUST reject a non-Git working directory, and MUST execute the command without evaluating concatenated command text. The launcher MUST preserve the caller's physical working directory when it is inside the project.

#### Scenario: Eligible project command

- **WHEN** an agent invokes the launcher with `--` followed by a command from inside a Git working tree
- **THEN** the launcher runs that command in the Bubblewrap sandbox from the original working directory

#### Scenario: Missing prerequisite

- **WHEN** Bubblewrap, Git project discovery, or user-namespace setup fails
- **THEN** the launcher exits without running the target command outside the sandbox

### Requirement: Default authority boundary

The standard launcher MUST use isolated user, process, IPC, UTS, cgroup, and network namespaces; disable further user namespaces; a private home; a cleared inherited environment; dropped capabilities; and a new terminal session. It MUST deny host networking and MUST NOT expose host credential directories, host configuration directories, control sockets, or writable host paths outside the current Git project. It MUST hide project secret files and MUST mount `.git/config` read-only. It MUST refuse to launch when a protected path is a symlink, has another hard link, or shares an inode with another project path.

#### Scenario: Standard sandbox environment

- **WHEN** a command runs through the standard launcher
- **THEN** it receives a private home and temporary directory, no inherited environment, no nested user namespace, and no host network interface

#### Scenario: Project write

- **WHEN** the launched command writes a project-relative file
- **THEN** the file write is permitted within the current Git project while the launcher exposes no other writable host path

#### Scenario: Aliased secret

- **WHEN** a protected secret file has another directory entry in the project
- **THEN** the launcher exits before executing the command

### Requirement: External approval records

The launcher MUST ignore repository `.bwrap.yaml`. Reusable exceptions MUST be the committed `.bwrap/approvals/` tree so every clone and collaborator shares them. The launcher MUST read that policy from `HEAD` and MUST ignore uncommitted working-tree edits. It MUST NOT store authority in a per-user home directory. The sandbox MUST NOT be able to rewrite `.bwrap`. Recording an exception MUST require the operator to confirm it on the controlling terminal, and that record MUST remain inactive until committed. Sandbox exceptions MUST match the exact command. Host execution MUST be limited to `git commit`, `git push`, and `pre-commit`, and MUST be refused when `core.hooksPath` is set or the reviewed hook and Git config fingerprint changed.

#### Scenario: Repository approval file

- **WHEN** the project contains `.bwrap.yaml` or an uncommitted `.bwrap/approvals/` record granting host execution
- **THEN** the launcher ignores it and runs the standard sandbox

#### Scenario: Committed shared policy

- **WHEN** `.bwrap/approvals/` is committed and another clone checks out that commit
- **THEN** the launcher applies the same exception without a per-user approval store

#### Scenario: Host interpreter request

- **WHEN** an approval requests host execution of an interpreter or an unlisted Git command
- **THEN** the launcher rejects the approval and does not run that command on the host

#### Scenario: Changed hooks

- **WHEN** hooks or `.git/config` change after a host approval was recorded
- **THEN** the launcher refuses host execution until a new approval is recorded

### Requirement: Scoped escalation guidance

The skill MUST require explicit approval before a command receives host networking, an additional mount, persistence outside the project, a secret, a socket, or a device. The approval MUST name the command, requested authority, and rationale. The launcher MUST reject mounts of the filesystem root, the home directory, credential directories, and the global pre-commit cache.

#### Scenario: Command requires network access

- **WHEN** a requested command cannot complete without networking
- **THEN** the skill reports that the standard sandbox denies networking and obtains explicit approval before proposing a separate narrowed invocation

### Requirement: Completion reporting

The skill MUST instruct agents to treat sandbox output as untrusted, inspect project status and relevant diffs after expected writes, and report the command, exit status, network state, write scope, changed files, and approved exceptions.

#### Scenario: Command changes a project file

- **WHEN** an isolated command completes after writing project files
- **THEN** the agent inspects Git status and reports the affected files and sandbox authority used

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
- **THEN** the agent reports the unavailable bootstrap dependency and does not retry with networking, additional mounts, or unsandboxed execution without explicit approval

### Requirement: Safe pre-commit cache exceptions

The skill MUST NOT expose the user's global writable pre-commit cache as a default workaround. Guidance for a cache exception SHALL prefer a fully initialized cache dedicated to the current project, read-only hook content, ephemeral writable state for locks, logs, and patches, and the existing explicit approval and completion-reporting requirements. The launcher MUST reject a mount of the global pre-commit cache.

#### Scenario: Global cache proposed as a workaround

- **WHEN** a failed isolated pre-commit run could be made to work by mounting the user's global cache
- **THEN** the skill rejects an automatic writable global-cache mount and explains the cache-poisoning and unrelated-source exposure risks

#### Scenario: Dedicated prepared cache is approved

- **WHEN** the operator explicitly approves an additional mount for a fully initialized project-dedicated pre-commit cache
- **THEN** the agent records the exact cache path and mount mode, preserves network isolation, exposes persistent hook content read-only, and keeps writable runtime state ephemeral

#### Scenario: Prepared hook requires cache mutation

- **WHEN** a hook cannot execute with its prepared persistent content mounted read-only
- **THEN** the agent stops and recommends a disposable environment rather than widening the persistent cache to writable access by default
