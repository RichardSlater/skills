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
reuse a published `v*` tag. New release tags are annotated and GPG-signed from
the exact planned SHA.

## Repository controls

Before enabling publication, maintainers must configure the `main` branch
ruleset to require the **conventional-commit-title** check and pull requests,
and enable squash merging. The squash title is the release contract; accepted
format is `type(scope optional)!: description`, for example `fix(parser):
handle empty input` or `feat!: remove legacy API`.

A `v*` tag ruleset must prevent tag update and deletion and allow creation only
by the repository's trusted GitHub App. Do not introduce a personal access token.

The `release` environment is attached only to the publishing job. It must allow
deployments from protected `main`. With no required reviewers publication is
automatic; required reviewers intentionally make only the final publish step
approval-gated while planning still runs automatically. Store the GitHub App ID
and private key as `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY`. Store a
dedicated release-only GPG private key, passphrase, and 40-character fingerprint
as `RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE`, and `RELEASE_GPG_KEY_ID`.
The current public key is [`release-signing-key.asc`](release-signing-key.asc)
with primary fingerprint `6B033F774359C7193A156138F21D1A5E9171C241`.
Rotate it by adding a new protected-environment key and fingerprint before
retiring the old public key.

## Retry and recovery

1. Inspect the failed workflow's planned SHA, SemVer, tag, and artifact.
2. Retry only when the planned SHA remains reachable from `main`.
3. If the expected tag targets that SHA but the release is missing, retry to
   create the missing release using the existing tag.
4. If both tag and release exist, treat the run as complete only when the tag
   verifies with the configured release key; assets are never replaced.
5. Each release publishes the ZIP, its `.sha256` manifest, and detached `.asc`
   signatures for both. GitHub also records build provenance for the ZIP. After
   downloading the assets, verify them with `sha256sum --check skills-VERSION.zip.sha256`,
   then use `gpg --verify` for both detached signatures with the published key.
   The immutable `v1.1.1` through `v1.1.4` manifests contain a transient runner
   path and cannot be checked after download; verify their ZIP detached signature
   directly instead. Do not replace these immutable assets.
6. If a tag targets another SHA, does not verify, or release state conflicts,
   stop and investigate. Never delete, move, or reuse a published tag to recover.

To roll back automation, disable the `push` trigger and restore a reviewed
manual-dispatch workflow. Rollback changes future execution only; it does not
mutate published tags or releases.
