# Automated releases

A push to protected `main` runs the automated release workflow. It uses the
canonical squash-merge commit message as the release input:

- `fix` creates a patch release.
- `feat` creates a minor release.
- `!` after a type or scope, or a `BREAKING CHANGE:` footer, creates a major release.
- Valid `build`, `chore`, `ci`, `docs`, `refactor`, `style`, and `test` commits do
  not independently publish a release. They remain in the generated-notes range
  until a later qualifying change is released.

The immutable `v1.0.2` tag is the current baseline. The next qualifying stable
release is calculated from that tag; maintainers must never move, delete, or
reuse a published `v*` tag.

## Repository controls

Before enabling publication, maintainers must configure the `main` branch
ruleset to require the **conventional-commit-title** check and pull requests,
and enable squash merging. The squash title is the release contract; accepted
format is `type(scope optional)!: description`, for example `fix(parser):
handle empty input` or `feat!: remove legacy API`.

A `v*` tag ruleset must prevent tag update and deletion and allow creation only
by the repository's trusted GitHub Actions publishing actor. The release workflow
uses its job-scoped `GITHUB_TOKEN`; do not introduce a personal access token.

The `release` environment is attached only to the publishing job. It must allow
deployments from protected `main`. With no required reviewers publication is
automatic; required reviewers intentionally make only the final publish step
approval-gated while planning still runs automatically.

## Retry and recovery

1. Inspect the failed workflow's planned SHA, SemVer, tag, and artifact.
2. Retry only when the planned SHA remains reachable from `main`.
3. If the expected tag targets that SHA but the release is missing, retry to
   create the missing release using the existing tag.
4. If both tag and release exist, treat the run as complete; assets are never
   replaced.
5. If a tag targets another SHA, or release state conflicts, stop and investigate.
   Never delete, move, or reuse a published tag to recover.

To roll back automation, disable the `push` trigger and restore a reviewed
manual-dispatch workflow. Rollback changes future execution only; it does not
mutate published tags or releases.
