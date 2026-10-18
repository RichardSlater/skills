## MODIFIED Requirements

### Requirement: Standard isolated invocation

The skill SHALL provide a launcher for a command argument array run from inside a Git working tree. The launcher MUST require Bubblewrap and a user namespace, MUST reject a non-Git working directory, and MUST execute the command without evaluating concatenated command text. The launcher MUST preserve the caller's physical working directory when it is inside the project.

#### Scenario: Eligible project command

- **WHEN** an agent invokes the launcher with `--` followed by a command from inside a Git working tree
- **THEN** the launcher runs that command in the Bubblewrap sandbox from the original working directory

#### Scenario: Missing prerequisite

- **WHEN** Bubblewrap, Git project discovery, or user-namespace setup fails
- **THEN** the launcher exits without running the target command outside the sandbox
