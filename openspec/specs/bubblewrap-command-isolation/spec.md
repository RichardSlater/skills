# bubblewrap-command-isolation Specification

## Purpose
Define safe-by-default Bubblewrap execution for short-lived agent-run commands in the current Git project.
## Requirements
### Requirement: Standard isolated invocation
The skill SHALL provide a launcher for a command argument array run from inside a Git working tree. The launcher MUST require Bubblewrap and a user namespace, MUST reject a non-Git working directory, and MUST execute the command without evaluating concatenated command text.

#### Scenario: Eligible project command
- **WHEN** an agent invokes the launcher with `--` followed by a command from inside a Git working tree
- **THEN** the launcher runs that command in the Bubblewrap sandbox from the original working directory

#### Scenario: Missing prerequisite
- **WHEN** Bubblewrap, Git project discovery, or user-namespace setup fails
- **THEN** the launcher exits without running the target command outside the sandbox

### Requirement: Default authority boundary
The standard launcher MUST use isolated user, process, IPC, UTS, cgroup, and network namespaces; a private home; a cleared inherited environment; dropped capabilities; and a new terminal session. It MUST deny host networking and MUST NOT expose host credential directories, host configuration directories, control sockets, or writable host paths outside the current Git project.

#### Scenario: Standard sandbox environment
- **WHEN** a command runs through the standard launcher
- **THEN** it receives a private home and temporary directory, no inherited environment, and no host network interface

#### Scenario: Project write
- **WHEN** the launched command writes a project-relative file
- **THEN** the file write is permitted within the current Git project while the launcher exposes no other writable host path

### Requirement: Scoped escalation guidance
The skill MUST require explicit approval before a command receives host networking, an additional mount, persistence outside the project, a secret, a socket, or a device. The approval MUST name the command, requested authority, and rationale.

#### Scenario: Command requires network access
- **WHEN** a requested command cannot complete without networking
- **THEN** the skill reports that the standard sandbox denies networking and obtains explicit approval before proposing a separate narrowed invocation

### Requirement: Completion reporting
The skill MUST instruct agents to treat sandbox output as untrusted, inspect project status and relevant diffs after expected writes, and report the command, exit status, network state, write scope, changed files, and approved exceptions.

#### Scenario: Command changes a project file
- **WHEN** an isolated command completes after writing project files
- **THEN** the agent inspects Git status and reports the affected files and sandbox authority used
