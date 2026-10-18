## Context

Isolation has to be enforced by the executable the agent invokes. Prose checks are skipped when the copied template is incomplete.

## Decisions

- The launcher owns mount construction, secret masking, and approval parsing.
- Approval records are the committed `.bwrap/approvals/` tree, so clones and collaborators share them. The launcher reads `HEAD` only and hides `.bwrap` from the sandbox.
- Host execution is an allowlist in code, not a prefix stored by the project.
- `core.hooksPath`, symlinked hooks, and hook/config fingerprint drift fail closed.
- Nested user namespaces are disabled with `--disable-userns`.

## Residual risk

A host-approved command still runs with host authority. The launcher cannot stop that command from later editing the external approval store. Forbidden mounts and the host allowlist still apply on the next launch.
