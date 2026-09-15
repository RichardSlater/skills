## Why

Agent-run project commands can execute untrusted code with access to host configuration, credentials, and network services. A reusable Linux isolation skill provides a safe default for short-lived local commands.

## What Changes

- Add a Bubblewrap isolation skill and a non-interactive launcher for commands in the current Git working tree.
- Deny networking and inherited environment by default, expose only required runtime files read-only, and keep the project as the sole writable host path.
- Document capability-escalation approval rules, output handling, and the boundary's limitations.

## Capabilities

### New Capabilities

- `bubblewrap-command-isolation`: Runs eligible project commands with bounded Bubblewrap filesystem, process, environment, and network access.

### Modified Capabilities

- None.

## Impact

Adds skill documentation, one Bash launcher, and the repository skill catalogue entry. Requires Linux, Bubblewrap, Git, Bash, and unprivileged user namespaces at use time.
