## Context

Skills install independently; runtime helpers must remain colocated. Security claims must be enforced at public entry points, not only helper unit tests.

## Goals / Non-Goals

Goals: no token output, immutable approved containers, bounded cancellable execution, confined file access, explicit disclosure consent, accurate analysis and provenance, verified signed commit.
Non-goals: execute suspicious code, change GitHub settings, autonomously merge, or publish ignored local agent files.

## Decisions

Use no-follow descriptor-relative reads/writes on POSIX, bounded subprocess capture with process-group termination, explicit container identity and cleanup, and one deadline per repository/Scorecard run. Parse workflow steps as YAML instead of regex. Fail closed on incomplete evidence. Preserve inherited permission scopes. Consent records name repository and destination. Offline assessment snapshots include HEAD/index/worktree bytes. Runtime wheels are hash-locked; network acquisition is separated from offline tests.

## Risks / Trade-offs

Fail-closed behavior can reject unsupported platforms or require new operator consent. Keep independent skill helpers synchronized and test their contracts. Real external Scorecard/API behavior is not exercised with private credentials during validation.
