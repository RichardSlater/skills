---
name: opsx-rightsize
description: Right-size an OpenSpec change against the original request while preserving its stated goal and validation. Use whenever an OpenSpec change has many tasks, appears over-engineered or over-complicated, or proposes significantly more work than the original prompt suggests; also use on explicit /opsx-rightsize requests before or during implementation.
compatibility: Requires openspec CLI and an OpenSpec root (openspec/ directory) or a registered store.
---

# OpenSpec right-size

Ask: **“Is this spec over-engineered or over-complicated? Can this change be made with minimal changes to the code and still achieve its stated goal?”**

Find the smallest sufficient implementation, not merely the shortest task list. Review first, obtain approval for a concrete simplification, then update only the selected change's artifacts and validate them.

## When to use

- A change has many tasks relative to its goal, especially before `/opsx-apply`.
- The proposal, design, or tasks ask significantly more than the original prompt suggested.
- New frameworks, dependencies, abstractions, migrations, or unrelated cleanup appear unnecessary.
- Implementation reveals a simpler path, or the operator explicitly invokes `/opsx-rightsize <change>`.

Task count is a review signal, not a fixed threshold or proof of over-engineering. A large but necessary change may already be right-sized. Do not force reductions.

## Inputs and selection

1. Resolve the OpenSpec root before selecting a change. For a named store, discover it with `openspec store list --json` and pass `--store <id>` consistently on all change commands, including listing. If the installed CLI lacks store support or the intended root/store is ambiguous, stop and ask rather than falling back to a different root.
2. Use the named active change, or run `openspec list --json` against the resolved root/store. If there are no active changes, stop and report that there is nothing to right-size. If there is exactly one, select it; if there are multiple, ask the operator to select one. Never silently choose among multiple active changes or edit archived changes.
3. Read `openspec status --change "<name>" --json` and `openspec instructions apply --change "<name>" --json`. Use the resolved change directory and context files rather than guessing paths. Status describes artifact completion, not task completion. If apply instructions are unavailable for an early-stage change, use the available artifact instructions and report missing inputs.
4. Read the original user prompt, subsequent explicit scope decisions, repository instructions, OpenSpec configuration, and selected schema instructions. Inspect enough of the available change artifacts and relevant code/tests to triage the scope. Before proposing edits, read all existing change artifacts and affected main specs, and inspect the relevant code and tests to substantiate reuse. Check working-tree changes before editing; preserve unrelated and pre-existing work.
5. If the original prompt is unavailable, ask for it or an operator-confirmed goal and non-goals. Do not treat an expanded proposal as evidence that all its scope was requested. If the prompt and stated goal conflict, resolve that conflict with the operator before proposing cuts.

## Workflow

### Quick triage

Compare the agreed goal with the plan's main work groups and any proposed new dependencies, abstractions, or migrations. Task count alone does not justify a full review.

If this inspection finds no concrete excess and there is enough evidence to judge the scope, report **already right-sized** with a brief rationale and leave artifacts unchanged. No comparison table, exhaustive acceptance mapping, or validation run is required for this read-only triage; state its limited scope and that validation was not run. If evidence is insufficient, report the uncertainty or ask for missing context rather than declaring the plan right-sized.

If there is a plausible simplification, continue with the full workflow below before proposing or making edits.

### 1. Establish the baseline

Restate the agreed goal, observable acceptance criteria, and explicit non-goals. Separate requested behavior from implementation choices added by the plan.

Run the selected change's validation before editing:

```bash
openspec validate "<name>" --strict
```

Include the selected store option when applicable. Record the command, exit status, and diagnostics. If validation already fails, distinguish existing failures from proposed changes; do not claim to preserve a passing baseline. Early-stage artifacts may be incomplete, and strict validation may still require delta specs for a custom schema. Record those limitations and any existing, documented spec exemption separately from regressions. Do not add an exemption, invent delta specs, or change validation configuration merely to obtain a pass. If the CLI, schema, or artifacts needed to assess the proposed cuts are unavailable, provide a read-only assessment and report the blocker instead of claiming validation succeeded.

### 2. Challenge the scope

For each requirement, design decision, and task group, ask:

- Which original goal or acceptance criterion requires this work?
- Can existing code, interfaces, dependencies, and tests satisfy it with a local change?
- Is this speculative extensibility, a generic framework for one use case, premature optimization, unrelated refactoring, or work for a hypothetical future requirement?
- Is a new dependency, configuration surface, migration, compatibility layer, or rollout mechanism actually necessary?
- Would removing it compromise correctness, security, compatibility, data integrity, required performance, or verifiability?
- Apply YAGNI and KISS principles. Avoid over-engineering, over-complication, and unnecessary abstractions. Do not assume that a safeguard is unnecessary; keep uncertainty visible and ask for confirmation.

Classify work as **keep**, **simplify**, **defer**, or **remove**, with evidence and a rationale. Keep uncertainty visible; ask rather than assuming a safeguard is unnecessary. Do not equate fewer lines, fewer files, merged task bullets, or deleted tests with lower implementation complexity.

### 3. Propose the minimum sufficient change

Present a compact comparison:

| Existing scope | Decision | Minimal alternative and rationale | Goal/test coverage retained |
| --- | --- | --- | --- |
| Requirement, design choice, or task group | Keep / simplify / defer / remove | Concrete code path or reuse opportunity | Acceptance criterion and verification |

Describe the proposed implementation boundary, affected artifacts, and expected reduction in actual code churn, dependencies, or moving parts. Map every acceptance criterion to retained work and verification. Identify deferred scope explicitly; do not create follow-up changes or issues automatically.

If no safe reduction exists, report **already right-sized** and leave artifacts unchanged. Otherwise, ask for explicit approval of the proposed artifact edits before writing. Automatic triggering authorizes review, not silent scope reduction. Any change to the agreed goal requires a separate explicit scope decision, not an incidental task deletion.

### 4. Update the approved artifacts coherently

Edit only the selected active change's artifacts within the approved boundary:

- **Proposal:** retain the goal and align scope, capabilities, impact, and non-goals with the smaller approach.
- **Design, when present or required:** replace unnecessary mechanisms with the agreed simpler design and document important tradeoffs.
- **Delta specs:** preserve required behavior and scenario coverage. Follow the selected schema's exact delta structure and requirement/scenario syntax. For spec-driven schemas, preserve valid ADDED/MODIFIED/REMOVED/RENAMED sections and required scenario headings; MODIFIED requirements must retain the complete intended requirement and its scenarios. Removing a proposed addition does not mean introducing a REMOVED requirement against the main spec.
- **Tasks:** retain concrete, verifiable implementation and validation steps, remove only approved unnecessary work, and keep dependency ordering coherent. Preserve completed-task history and checkbox truth; do not mark pending work complete or erase completed work to improve the counts. If an approved simplification needs rework, add an honest unchecked follow-up task.

Use the actual schema's artifact names and rules rather than forcing these filenames onto a custom schema. Check cross-artifact references and capability names for consistency. Do not modify main specs, application code, tests, schema definitions, or validation configuration; do not implement, archive, commit, or publish the change from this skill.

### 5. Validate and review

Re-run the same strict validation against the same change and store. Inspect the diff and confirm that:

- every agreed acceptance criterion still has evidence appropriate to the selected schema and a verification path: requirements/scenarios where required, or explicit acceptance checks in the schema's artifacts otherwise;
- all applicable change artifacts agree on the reduced scope;
- required security, compatibility, migration, rollback, and test coverage remain where applicable;
- no unrelated files or pre-existing operator edits were overwritten.

Strict validation checks structure, not whether the goal is still met; both checks are required. Fix regressions introduced by the edits within the approved boundary and rerun validation. Never weaken validation, suppress errors, or remove required scenarios just to obtain a pass. If validation remains blocked, report the exact failure and affected edits, do not declare completion, and offer to undo only this skill's edits without reverting pre-existing work.

## Completion report

For quick triage, report only the change/store, agreed goal, verdict, brief supporting rationale, and that no artifacts changed or validation ran. For the full workflow, report:

- **Change/store** and agreed goal.
- **Verdict:** already right-sized, simplified, or blocked.
- **Scope:** what was kept, simplified, removed, or deferred, and why.
- **Artifacts changed:** exact paths, or none for a read-only review.
- **Coverage:** how the smaller plan still achieves every acceptance criterion.
- **Validation:** baseline and final command results, including unresolved failures.
- **Next step:** operator decision if blocked, otherwise resume the appropriate OpenSpec planning or apply workflow.

Never claim application tests passed when only OpenSpec validation ran.

## Example

A plan introduces a new service and configuration layer for behavior already supported by an existing helper. Propose a local helper change and focused regression test instead, showing which acceptance criteria they retain. Obtain approval before updating the plan; do not implement the helper change from this skill. If the separate service is required for isolation or compatibility, keep it and explain why.
