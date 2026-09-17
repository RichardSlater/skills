## Context

The standard launcher intentionally clears the environment, replaces `HOME`, restricts `PATH`, and removes networking. Those controls work well for self-contained commands, but `pre-commit` is both a quality-gate runner and an environment bootstrapper. Its first run normally clones hook repositories and installs language-specific environments beneath `PRE_COMMIT_HOME`; user installations also commonly live beneath the inaccessible host home.

Investigation confirmed three distinct outcomes:

- a fresh sandbox fails while fetching remote hook repositories;
- the sandbox can select a different system `pre-commit` than the host command;
- a fully initialized hook cache can support an offline run when hook content is exposed read-only and transient state remains writable.

The existing no-network and no-host-home guarantees must remain the default.

## Goals / Non-Goals

**Goals:**

- Make agents recognize `pre-commit` and similar bootstrap-dependent commands before attempting a quality gate.
- Require verification of the executable and version visible inside the sandbox.
- Explain the supported offline cases and the failure signals that require stopping.
- Preserve explicit approval for every additional mount, network capability, or unsandboxed execution.
- Prevent writable global cache exposure and accidental disclosure of unrelated or private hook repositories.

**Non-Goals:**

- Add network access to the standard launcher.
- Automatically mount the host home or global pre-commit cache.
- Build a general dependency-cache manager or network broker.
- Guarantee that every third-party pre-commit hook can run read-only or offline.
- Change repository pre-commit configuration or dependency versions.

## Decisions

### Treat pre-commit as conditionally compatible

The skill will describe pre-commit as compatible with the standard sandbox only when the executable and all hook dependencies are already available through paths visible in the sandbox. Agents will first run an isolated version probe and compare the result with any host-side command they intended to use.

This is preferred over assuming `command -v pre-commit` on the host is sufficient, because the sandbox's fixed `PATH` and inaccessible home can select another installation or none at all.

### Keep initialization outside the standard authority boundary

A missing remote repository or language environment will be treated as an expected offline-bootstrap failure. The agent will stop, explain that initialization requires authority absent from the standard sandbox, and request approval for a separate remedy.

The skill will not automatically rerun with `--share-net` or outside Bubblewrap. Automatic escalation would violate the existing scoped-exception contract and could expose local network services to untrusted installation code.

### Prefer self-contained hooks, then dedicated caches

The documented preference order will be:

1. local or vendored hooks whose executables and dependencies are project-visible;
2. a fully prepared cache dedicated to the current project and exposed read-only through an explicitly approved mount, with logs, locks, and patches written to ephemeral storage;
3. a disposable container or VM for network-dependent initialization;
4. an explicitly approved unsandboxed run when the operator accepts that risk.

A user's global pre-commit cache will not be the default cache source. It can contain unrelated or private repositories, and a writable mount would permit cross-project cache poisoning.

### Tune instructions before extending the launcher

This change will primarily update `SKILL.md` and its specification. It will not add a cache-mount option to `run-isolated.sh`; such an option would create a new authority-bearing interface and requires a separate design covering cache preparation, absolute paths in pre-commit's database, concurrency, confidentiality, and lifecycle.

Focused validation will assert the presence of the preflight, stop conditions, and cache-safety guidance. Existing launcher behavior will remain unchanged.

## Risks / Trade-offs

- **[Prepared caches are not universally read-only]** Some hooks may try to mutate their installed environment. → Document that such hooks are incompatible with the read-only-cache pattern and require a disposable environment.
- **[Version probes add an extra invocation]** Validation takes slightly longer. → Keep the probe small and only require it for bootstrap-dependent tooling.
- **[Guidance cannot detect every bootstrap mechanism]** Tools other than pre-commit may fail differently. → Describe the general cache/bootstrap pattern while giving pre-commit-specific examples.
- **[Unsandboxed execution remains an available exception]** Operator approval can accept more risk than ideal. → Require the exact command, rationale, and residual risk to be reported.
- **[A project-local writable cache is persistent project state]** Hooks could poison later runs. → Do not recommend it as the default; prefer read-only prepared inputs and ephemeral writable state.

## Migration Plan

1. Add the bootstrap-dependent quality-gate guidance to the skill.
2. Add focused validation for the required safety language and unchanged launcher boundary.
3. Run repository quality gates.
4. Archive the OpenSpec change before the final commit and pull request.

Rollback consists of reverting the documentation, validation, and specification changes; the launcher interface and default sandbox behavior are unchanged.

## Open Questions

- A future change may design a first-class dedicated-cache option after deciding how caches are prepared, scoped, verified, and garbage-collected.
- A future networked sandbox design could evaluate `slirp4netns` or a filtered proxy, but unrestricted egress and access to host-local services remain outside this change.
