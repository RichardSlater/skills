## Context

The repository currently has a `GitVersion.yml` baseline and a manually dispatched `.github/workflows/release.yml`. A maintainer must calculate and create a protected tag, enter it as workflow input, and then approve publication. The workflow packages content read-only and grants `contents: write` only to its publishing job, but it does not execute GitVersion. GitHub-generated release notes are already used.

The repository receives both maintainer and Dependabot changes and its history contains squash-style Conventional Commits, GitHub merge commits, and older free-form commits. Automated versioning therefore needs a single, validated commit convention at the protected `main` boundary. Publication must remain compatible with pinned actions, protected history, release-tag rulesets, and the existing `release` environment.

The desired flow is:

```text
pull request                           push to protected main
     │                                           │
     ▼                                           ▼
validate Conventional Commit      serialize release evaluation
metadata                                       │
     │                               ┌───────────▼───────────┐
     └── required status check ─────▶│ read-only plan/package│
                                     │ GitVersion + archive  │
                                     └───────────┬───────────┘
                                           no signal ──▶ stop
                                                 │ signal
                                                 ▼
                                      release environment
                                                 │
                                                 ▼
                                      publish job only
                                      `contents: write`
                                                 │
                                      tag exact SHA + release
```

## Goals / Non-Goals

**Goals:**

- Automatically evaluate every change reaching `main` and publish a stable release only when Conventional Commits requires a SemVer increment.
- Make `fix`, `feat`, `!`, and `BREAKING CHANGE:` the release contract while allowing other Conventional Commit types without releasing them.
- Use GitVersion, complete Git history, and existing SemVer tags as the version authority.
- Ensure the tag, archive, notes, and GitHub release refer to one immutable commit.
- Preserve least privilege: workflow default permissions are empty, planning and packaging are read-only, and only the publishing job has `contents: write`.
- Make overlapping runs, retries, and partial publication safe.
- Improve release notes without introducing a manually maintained version or changelog step.

**Non-Goals:**

- Publishing a release for `chore`, `docs`, `ci`, `build`, `test`, `style`, `refactor`, or other non-breaking types.
- Introducing additional release meanings for non-standard types such as `security` or `perf`; contributors use `fix` when a change warrants a patch release.
- Supporting prerelease channels, release branches, or manually selected versions in the initial automation.
- Mutating repository rulesets, environment configuration, or merge settings from the workflow.
- Adding long-lived personal access tokens or relying on a second tag-triggered workflow.
- Automatically editing `CHANGELOG.md` as part of publication.

## Decisions

### 1. Run one serialized workflow on pushes to main

Replace the tag-input `workflow_dispatch` path with a workflow triggered by pushes to `main`. Apply workflow-level concurrency with cancellation disabled so only one release evaluation can observe and mutate release state at a time. A later run starts after an earlier run publishes and therefore calculates against the newly created tag.

A single workflow avoids the GitHub behavior where a tag pushed with the repository `GITHUB_TOKEN` does not normally trigger another workflow. It also keeps the calculated version, packaged artifact, immutable SHA, and publication in one auditable run.

**Alternatives considered:**

- A tagger workflow followed by a tag-push release workflow requires a GitHub App token, PAT, or additional orchestration solely to cross the workflow-trigger boundary.
- `workflow_run` can chain privileged publication but makes data transfer, trust review, and retry behavior more complex.
- Keeping manual dispatch removes timing automation and retains unnecessary human input.

### 2. Use squash-merge metadata as the release contract

New pull requests SHALL present a valid Conventional Commit header as their title, and repository documentation SHALL identify squash merge as the expected merge strategy. A required pull-request validation check validates the title before merge. The resulting commit on `main` becomes the canonical release input; scopes are accepted but do not affect versioning.

GitVersion SHALL be configured with Conventional Commit bump expressions that recognize:

- `fix` as patch;
- `feat` as minor;
- a Conventional Commit `!` marker or `BREAKING CHANGE:` footer as major;
- no increment for other types unless a breaking marker is present.

The validation and GitVersion expressions must have shared test fixtures covering scoped commits, breaking syntax, non-releasing types, malformed headers, and precedence. This prevents the validator and version calculator from silently disagreeing.

**Alternatives considered:**

- Inspecting every branch commit makes release behavior depend on merge strategy and exposes intermediate commits that were not intended as release metadata.
- Inventing patch behavior for `chore`, `perf`, or custom types departs from the requested Conventional Commits SemVer contract.
- PR labels provide editorial control but are not the requested commit-driven source of truth.

### 3. Let GitVersion calculate; gate publication on a release signal

The read-only planning job checks out the exact triggering SHA with complete history and tags, executes a pinned GitVersion tool/action, and emits a validated version, tag, previous tag, release-required flag, and commit SHA. The release-required decision is based on the configured Conventional Commit increment rules, not merely on GitVersion producing an informational build version.

If the unreleased range has no release signal, the run reports a successful no-op. Those commits remain after the last release tag and are included when a later `fix`, `feat`, or breaking change causes publication.

The repository already has immutable `v1.0.0`, `v1.0.1`, and `v1.0.2` tags, so GitVersion uses `v1.0.2` as the release baseline. A no-tag temporary-history fixture continues to verify GitVersion's default `0.1.0` bootstrap, but it is not the policy for this repository. The implementation must dry-run GitVersion against current history before enabling the push trigger and confirm that the next calculated stable release is `v1.0.3`.

**Alternatives considered:**

- A custom SemVer calculator would duplicate GitVersion and make the existing configuration misleading.
- Tagging every push and using prerelease/build metadata would publish non-user-facing maintenance changes.

### 4. Separate read-only planning from repository mutation

The workflow SHALL declare `permissions: {}` at workflow scope. Jobs use the following permission boundary:

| Job | Permission | Responsibility |
|---|---|---|
| plan/package | `contents: read` | Checkout full history, run GitVersion, validate outputs, create archive, upload ephemeral artifact |
| publish | `contents: write` | Download the prepared artifact, revalidate release state, create tag, generate notes, create GitHub release |

No workflow-wide write grant is permitted. Checkout uses `persist-credentials: false`. The automatic token is exposed as `GH_TOKEN` only to the publication step that needs it. The publication job does not execute repository-provided build scripts and consumes only validated scalar outputs and the packaged artifact from the trusted `main` run.

The existing `release` environment remains attached to the publishing job as a policy and audit boundary. To meet fully automatic publication, it must permit deployments from protected `main` without a required human reviewer. Repositories that retain required reviewers intentionally convert the final step to approval-gated publication without changing version calculation.

**Alternatives considered:**

- Workflow-level `contents: write` gives every job unnecessary mutation capability.
- Persisting checkout credentials makes accidental `git push` possible from read-only steps.
- A PAT adds rotation and blast-radius risks without providing value in the single-workflow design.

### 5. Bind every output to the triggering SHA

The planning job records `github.sha`, packages files from that checkout, and validates calculated versions against strict SemVer/tag patterns before exposing outputs. The publishing job rechecks that the SHA is reachable from `main` and uses that SHA explicitly as the tag target. It never resolves the moving head of `main` during publication.

Create an annotated `v{major}.{minor}.{patch}` tag through the GitHub API and then create the GitHub release for that tag. The release title, archive filename, and tag all derive from the validated GitVersion SemVer. Repository tag rulesets must allow the trusted GitHub Actions actor to create, but not move or delete, matching release tags.

### 6. Make publication idempotent and recoverable

Immediately before mutation, the publishing job checks tag and release state:

| Existing state | Behavior |
|---|---|
| No tag, no release | Create the tag, then create the release |
| Tag targets expected SHA, no release | Reuse the immutable tag and create the missing release |
| Tag and release both exist | Complete as an idempotent no-op; never replace assets |
| Tag targets another SHA | Fail closed and require investigation |
| Release exists without the expected tag | Fail closed and require investigation |

This handles a failure between tag creation and release creation without moving a tag or calculating a replacement version. The one-workflow concurrency lock prevents ordinary races; state revalidation protects against external mutations and retries.

### 7. Keep GitHub-generated release notes, with repository configuration

Continue using GitHub-generated release notes between the previous and new tags. Add or refine `.github/release.yml` categories and exclusions so dependency-only and explicitly skipped pull requests do not dominate user-facing notes. Conventional Commit titles improve the source text, while labels can group features, fixes, documentation, and maintenance without affecting SemVer.

`CHANGELOG.md` remains a curated project overview rather than a publication input. Documentation must make that distinction explicit to avoid implying that its `Unreleased` section is automatically consumed.

**Alternatives considered:**

- Conventional-changelog would add another parser and release dependency alongside GitVersion.
- Automatically rewriting the changelog would require committing back to protected `main`, creating recursion and additional write permissions.

## Risks / Trade-offs

- **[Existing merge strategy or historical messages do not match the new contract]** → Enforce validation for new PRs, document squash merging, and bootstrap from a verified release baseline so older history is not repeatedly interpreted.
- **[GitVersion regexes and validation rules diverge]** → Maintain shared representative fixtures and test both release classification and configured GitVersion output.
- **[The calculated version differs from the immutable `v1.0.2` lineage]** → Run a no-write migration rehearsal against full history and investigate configuration or tag history before enabling automatic publication.
- **[A workflow run creates a tag but fails before creating the release]** → Reuse an existing tag only when it targets the expected SHA; otherwise fail closed.
- **[Tag rulesets reject the automatic token]** → Document and verify a narrowly scoped bypass for the trusted publishing workflow/actor before activation; do not fall back to a PAT.
- **[Generated notes include non-releasing maintenance accumulated since the previous tag]** → Configure release-note exclusions and allow `skip-changelog`-style labels while keeping version semantics commit-driven.
- **[Automatic releases publish more often than desired]** → Only `fix`, `feat`, and breaking changes trigger publication; changing cadence later requires an explicit policy change.
- **[A compromised third-party action reaches the write job]** → Pin actions by full commit SHA, minimize publish-job steps, avoid checkout/execution there, and grant only `contents: write` at job scope.
- **[Required environment reviewers prevent full automation]** → Treat this as an explicit repository policy choice and document that reviewers make publication approval-gated rather than automatic.

## Migration Plan

1. Add automated tests for Conventional Commit classification, precedence, malformed metadata, no-release behavior, and GitVersion output using representative repository history.
2. Configure GitVersion for Conventional Commit increments and verify both a no-tag fixture bootstrap and the current `v1.0.2` latest-tag calculation locally or in a read-only workflow run.
3. Add the pull-request title validation check and make it required in the protected `main` ruleset; configure squash merge as the supported merge method.
4. Refactor the release workflow into serialized read-only planning/packaging and job-scoped write publication, initially retaining a non-mutating rehearsal mode.
5. Verify the `release` environment and `v*` tag ruleset permit only the intended trusted actor and decide whether the environment has human approval.
6. Run a rehearsal on the current `main` SHA and inspect the calculated version, archive, release notes, permissions, and immutable targets.
7. Enable the `push` to `main` trigger and remove the maintainer-supplied tag path after the rehearsal passes.
8. Update release, contributing, and recovery documentation.

Rollback consists of disabling the automatic push trigger and restoring manual dispatch. Published tags remain immutable; rollback must never delete, move, or reuse a released version.

## Open Questions

- Does the repository's current ruleset already enforce squash-only merging and permit the GitHub Actions actor to create protected `v*` tags? This must be verified as repository-setting evidence during implementation.
- Does the existing `release` environment require reviewers? If so, maintainers must choose between retaining approval-gated publication and removing that reviewer requirement for fully automatic release creation.
