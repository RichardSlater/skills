## ADDED Requirements

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
The skill MUST NOT expose the user's global writable pre-commit cache as a default workaround. Guidance for a cache exception SHALL prefer a fully initialized cache dedicated to the current project, read-only hook content, ephemeral writable state for locks, logs, and patches, and the existing explicit approval and completion-reporting requirements.

#### Scenario: Global cache proposed as a workaround
- **WHEN** a failed isolated pre-commit run could be made to work by mounting the user's global cache
- **THEN** the skill rejects an automatic writable global-cache mount and explains the cache-poisoning and unrelated-source exposure risks

#### Scenario: Dedicated prepared cache is approved
- **WHEN** the operator explicitly approves an additional mount for a fully initialized project-dedicated pre-commit cache
- **THEN** the agent records the exact cache path and mount mode, preserves network isolation, exposes persistent hook content read-only, and keeps writable runtime state ephemeral

#### Scenario: Prepared hook requires cache mutation
- **WHEN** a hook cannot execute with its prepared persistent content mounted read-only
- **THEN** the agent stops and recommends a disposable environment rather than widening the persistent cache to writable access by default
