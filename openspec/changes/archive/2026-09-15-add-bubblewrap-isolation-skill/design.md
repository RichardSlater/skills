## Context

The repository distributes reusable agent skills. Bubblewrap offers Linux namespaces and explicit mount construction, but raw invocations are easy to weaken accidentally. The user selected project-only filesystem access and no network as defaults.

## Goals / Non-Goals

**Goals:**

- Provide a repeatable launcher that avoids shell evaluation and starts from an empty Bubblewrap filesystem.
- Make the current Git project the only writable host path and prevent inherited credentials/configuration.
- Require explicit approval before broader authority is added.

**Non-Goals:**

- Replace VM/microVM isolation for hostile workloads.
- Support interactive, privileged, networked, GUI, or credentialed commands by default.
- Guarantee CPU or memory limits beyond the bounded temporary filesystem.

## Decisions

- Use `--unshare-user --unshare-all`, `--new-session`, `--die-with-parent`, capability dropping, and a cleared environment. This establishes namespace and terminal isolation; raw host execution was rejected because it has no boundary.
- Bind `/usr` and conventional executable/library paths read-only, and bind the physical Git root writable at its original path. This supports ordinary host tools and project-local shebangs without mounting host home/configuration. Binding `/` was rejected because it exposes secrets and unrelated files.
- Use a private 1 GiB `/tmp` for the private home and transient data. Persisting host-home caches was rejected because it introduces credentials and broad host visibility.
- Deny networking by retaining Bubblewrap's new network namespace. Restoring host networking is a deliberate, separately approved exception rather than an option of the standard launcher.

## Risks / Trade-offs

- [Commands need unavailable runtime files] → identify the exact missing resource and obtain scoped approval; never widen mounts by guesswork.
- [Writable project is destructive] → inspect intended writes and review status/diff after execution.
- [Kernel or Bubblewrap vulnerability] → describe the boundary honestly and use a VM/microVM for stronger isolation.
- [No host cache/network] → require deterministic project-local inputs or an explicitly approved alternative.

## Migration Plan

Install the new skill with the repository's normal skills installer. No existing command behavior changes. Remove the skill directory and README entry to roll back.

## Open Questions

None.
