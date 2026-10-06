---
name: opsx-handoff
description: Persist in-flight OpenSpec change context to a HANDOFF.md so a fresh /opsx-apply session can resume implementation. Use when session context is about to be cleared, compaction is expected, or an OpenSpec change's implementation is being paused or interrupted.
compatibility: Requires openspec CLI and an OpenSpec root (openspec/ directory) or a registered store.
---

# OpenSpec handoff

When implementation of an OpenSpec change is in flight and the current session is about to end, write a `HANDOFF.md` in the change directory. Its purpose is to persist what this session knows beyond what `proposal.md`, `design.md`, the delta specs, and `tasks.md` already record, so context can be cleared and a new `/opsx-apply <change>` session can resume without re-deriving the work.

## When to use this skill

Use this skill when the operator wants to:

- clear or reset the session context while a change is still in flight;
- pause work that will be resumed in a later session;
- anticipate heavy context compaction during a long implementation; or
- hand the change to another session, operator, or agent.

An explicit request to "hand off", "save state", or "write a handoff" is sufficient to proceed.

## When not to use this skill

Do not use this skill when:

- no change has partial progress or active work in this session — there is nothing to hand off;
- the change is fully implemented — suggest archiving with `/opsx-archive` instead; or
- the operator wants to revise the plan rather than pause — use `/opsx-update` instead.

## Steps

Before any handoff, ensure that the OpenSpec change is fully up-to-date, tasks that are complete must be checked off, a `HANDOFF.md` is not a substitute for proper OpenSpec housekeeping, and the operator is ready to clear session context.

1. **Select the change(s)**

   Run `openspec list --json` and select the change(s) actually being worked on: those with partial task progress or active references in the current session (files touched, commands run, decisions made). If the operator named a change, use it. If no change is in flight, stop and say so — do not invent a handoff.

   **Store selection:** If the work lives in a named store, run `openspec store list --json` to discover the store id and pass `--store <id>` on the commands below, as the apply skill does. Without a store, commands act on the nearest local `openspec/` root.

2. **Check state**

   For each selected change:

   ```bash
   openspec status --change "<name>" --json
   ```

   Use the progress (complete / total / remaining) and `changeRoot` to ground the handoff in the actual task state.

3. **Gather implementation context**

   Review the current session, plus `git status` and `git log` for uncommitted or recent work, and collect everything **not** already captured in the change's artifacts:

   - **Progress beyond checkbox state** — what the in-flight task actually entails, what is half-done, and how to finish it.
   - **Decisions made** — implementation choices and tradeoffs not yet recorded in `design.md`.
   - **Working-tree state** — branch, commits, uncommitted or WIP changes, and anything that must not be lost or clobbered on resume.
   - **Verification state** — which builds, tests, and linters pass or fail, and why known failures fail.
   - **Pitfalls** — constraints, surprises, environment quirks, and rejected approaches the next session should not rediscover.
   - **Next actions** — the ordered steps the resuming session should take first.
   - **Open questions** — anything requiring an operator decision.

4. **Write `HANDOFF.md`**

   Write (or replace) `<changeRoot>/HANDOFF.md` — the change directory alongside `proposal.md`, `tasks.md`, and `specs/`, not the main spec tree or the archive. If one already exists, replace it with the current state instead of appending. Do not edit the change's other artifacts from a handoff.

   Use this structure, omitting any section that has nothing to say:

   ```markdown
   # Handoff: <change name>

   _Updated: <YYYY-MM-DD HH:MM> · Task progress: <complete>/<total> · State: <one-line summary>_

   ## Current position
   Where work stopped, which task is in flight, and how to finish it.

   ## Decisions made
   Implementation decisions not yet reflected in design.md, with rationale.

   ## Working tree state
   Branch, commits, uncommitted changes, anything to preserve or not clobber.

   ## Verification
   Build/test/lint status and known failures with causes.

   ## Pitfalls and constraints
   Surprises, rejected approaches, environment quirks.

   ## Next actions
   Ordered steps for the resuming session.

   ## Open questions
   Items requiring an operator decision, if any.
   ```

   Every section must add information beyond the change's artifacts. Never restate the spec, paraphrase the task list, or copy artifact content.

5. **Confirm and report**

   After writing, tell the operator:

   - the path of the handoff and which changes were covered;
   - that session context can now be cleared; and
   - that work resumes with `/opsx-apply <change>`.

## Guardrails

- Write only `HANDOFF.md`; do not modify `proposal.md`, `design.md`, delta specs, or code from a handoff.
- One handoff per change directory; the newest state replaces the old.
- Never record secrets, tokens, or credentials.
- Never mark a task complete to make the handoff look tidier — checkbox state in `tasks.md` stays authoritative.
- If the session state is too thin to be worth persisting, say so instead of writing a low-value file.

## Output on completion

```text
## Handoff Written

**Change:** <change-name>
**Progress:** N/M tasks complete
**Handoff:** openspec/changes/<change-name>/HANDOFF.md

Context can now be cleared. Resume with `/opsx-apply <change-name>`.
```
