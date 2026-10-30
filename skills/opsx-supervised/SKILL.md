---
name: opsx-supervised
description: >
  Implement OpenSpec changes using supervised subagents. Use when the user
  requests supervised or unattended OpenSpec implementation, including
  continuing an incomplete change.
---

# OpenSpec Supervised Implementation

Supervise implementation with `pi-subagents`. The supervisor owns planning,
integration, acceptance and OpenSpec task updates. Delegate bounded work to
configured agents; do not delegate publication or user decisions. Continue
without routine prompts, but stop or isolate a lane when safe progress requires
user input.

## 1. Discover and preflight

1. Select the requested change. If unspecified, infer it from context or use
   `openspec list --json`; ask the user if multiple changes remain plausible.
   Announce the selected change.
2. Run `openspec status --change <name> --json` and
   `openspec instructions apply --change <name> --json`. Follow the returned
   state and read every listed `contextFiles` path. If blocked by missing
   artifacts, report the blocker; if already complete, report completion.
3. Load the `pi-subagents` skill and use its current guides for workflows,
   worktrees and configuration. Run `subagent({ action: "doctor" })` and
   check agent and model availability. Identify the effective models and tools
   for `worker`, `reviewer`, and, when needed, `scout` and `oracle`.
4. Check the working tree and preserve existing changes. Identify task
   dependencies, validation commands, write boundaries and available isolation.
5. Establish the resource policy below before launching concurrent children.
   Report the selected roles, resource limits and any configuration blockers.

If the extension, a required role, model, tool or credential is unavailable,
report the exact diagnostic and recommend an appropriate configuration fix.
Use `subagent({ action: "models" })` to inspect available models. Configuration
resolution does not prove provider connectivity or quota; report runtime errors
when they occur. Do not silently substitute a model, switch execution methods,
or change user configuration. Follow the `pi-subagents` failure procedure and
preserve partial work. Continue independent lanes only when they remain safe.

Model overrides belong in user or project Pi settings under
`subagents.agentOverrides`; recommend provider-qualified IDs resolved by the
installed environment, rather than prescribing specific model names. The
`pi-subagents` configuration guide describes `globalConcurrencyLimit` in its
own config file and workflow overrides. It limits all children within a run,
not individual providers or other runs.

## 2. Set resource limits

Use operator-provided deployment and capacity information, not model names, to
map each effective model to its inference resource. For example, all models on
one machine may share one slot, while hosted models can use separate capacity.
Group aliases or providers sharing the same local hardware. Report the mapping;
ask for unknown local/shared resource mappings or limits before running
potentially competing requests. Do not assume that a provider or model is local
or hosted from its name alone. Review `AGENTS.md` for providers and models that
are known to share local resources.

- Default each local resource to at most one active child. Honor an explicitly
  lower operator limit, and raise the default only with explicit approval.
- Keep the local slot occupied until the child actually settles, including
  failures and cancellations; an uncertain outcome retains the slot until
  resolved. Never launch another child against that resource while it is held.
- Use the configured overall run limit and operator-specified hosted limits;
  respect provider rate limits and any cost or usage budget. If hosted capacity
  is unknown, use a modest bounded fanout rather than unlimited launches.
- Within one workflow, queue local children by resource and launch independent
  hosted children when their capacity permits. Use `pi-subagents` workflow
  primitives and completion notifications; do not poll or build a separate
  scheduler service. Treat the run-wide `globalConcurrencyLimit` as an
  additional ceiling, not as a per-provider limit.

This admission policy governs only children controlled by this workflow. It
cannot exclude the supervisor's own requests, other runs, sessions or external
clients. If those may share a local resource, require server-side queuing or
another operator-confirmed shared concurrency control before claiming exclusive
use. If it cannot be established, pause work on that resource and explain the
limitation; independent safe work can continue.

## 3. Plan and dispatch

Select ready, incomplete tasks and group related small units when this reduces
round trips without weakening acceptance. For each unit define its OpenSpec task
identifiers, objective, relevant context, edit boundaries, acceptance criteria,
validation and dependencies. Use `scout` when exploration is necessary.

Launch independent units as capacity permits. For parallel writing use separate
managed worktrees, one writer per worktree, and retain the resulting handoff
and patch evidence. Worktrees require a clean source checkout; if unavailable,
use one writer in the existing checkout and preserve existing changes. Do not
stash, commit, discard changes or silently drop isolation. Parallelize safe
read-only work when capacity permits.

Give each `worker` a self-contained contract: goal, repository and ref,
authority, files and constraints, validation, expected report and stop conditions.
Workers make focused changes, report files, checks and blockers, and never mark
OpenSpec tasks complete. Do not use tight hard tool budgets on writing workers.

## 4. Integrate, validate and review

As children settle, inspect their results and launch newly ready work without
waiting for unrelated lanes. Integrate patches serially, preserving unrelated
changes and checking for conflicts and stale assumptions. Verify applicable
checks using trustworthy worker evidence or rerun them when integration or
uncertainty warrants it. Run cross-lane checks after integration where changes
may interact.

Delegate fresh-context independent review to `reviewer`, allowing related units
to share a review. Require an ACCEPT, REVISE or BLOCKED verdict with evidence;
compare the result against the OpenSpec requirements. A successful child run or
a worker's self-assessment is not acceptance.

For corrections, give bounded feedback and allow at most two attempts before
escalating to `oracle` or reporting a blocker. Do not repeat an unchanged
approach. If a requirement or architectural decision needs user approval, pause
the affected lane while continuing unrelated safe work.

After each OpenSpec task's implementation, integration, validation and review
are complete, mark its original checkbox complete without changing its
identifier or description. Do not mark incomplete, failed or unverified tasks
complete. Refresh OpenSpec status and continue ready work until all tasks are
complete or no safe progress remains.

## 5. Report

Summarize completed tasks, changed files, validation and review evidence,
blocked or pending work, configuration/resource warnings and any decisions
needed. State whether changes were only local or were committed or published.
Avoid verbose child transcripts.
