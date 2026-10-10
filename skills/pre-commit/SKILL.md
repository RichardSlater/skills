---
name: pre-commit
description: Validate repository pre-commit gates before committing or pushing. Use when a repository has .pre-commit-config.yaml; inspect prerequisites, preserve user changes, run all configured gates, and retain required commit signing.
compatibility: Git and the repository-approved pre-commit installation; hook runtimes vary by repository.
---

# Pre-commit workflow

Use the target repository's actual configuration, not assumptions from another
clone. A pre-commit configuration does not prove the Git hook is installed.

## Preflight

1. Read `.pre-commit-config.yaml` and the repository's contribution instructions.
2. Identify the required Python, Node, Go or other runtimes and locked dependencies.
   Use reviewed, hash-locked dependencies; do not install mutable latest versions.
3. Verify `pre-commit --version` and inspect the configured Git hooks directory.
   If the hook is missing, ask the operator to run `pre-commit install` or obtain
   approval to install it. Run the quality gate even when no hook is installed.
4. Follow the active isolation policy. Host-side hooks are acceptable only for
   trusted repositories where the operator has authorized that standardized
   workflow; this skill never grants an exception for suspicious target code.

## Validate before committing

Run the configured full gate:

```bash
pre-commit run --all-files
```

Record results. If any hook fails or changes files, inspect the changes, preserve
unrelated edits, stage only intended fixes, and rerun until all gates pass. Never
use `SKIP`, `--no-verify`, blanket recovery staging, or lower thresholds to make
a commit pass. During `git commit`, hooks may separately inspect staged content.

Pre-commit can temporarily stash unstaged tracked changes. Hooks that change
files abort the commit and do not stage their fixes. Restoration conflicts can
roll back hook fixes. Inspect `git status --short`, `git diff` and
`git diff --cached` before retrying; do not overwrite the operator's work.

## Repository-specific prerequisites

Only export variables documented by the current repository. For example, a
repository whose configuration hook explicitly uses `QUALITY_PYTHON` may need:

```bash
export QUALITY_PYTHON="$PWD/.quality-venv/bin/python"
```

Do not assume this environment exists or is needed. Confirm the configuration
hook actually references it; create an ignored environment from that repository's
hash-locked requirements only after installation approval. Do not copy reapers-
arsenal paths, cache locations, hook versions or latency estimates to another
repository.

## Secret diagnostics

Use the repository-approved secret scanner with full redaction. Scan the complete
intended commit, including new files, and any PR body. Keep diagnostics outside
the repository in private storage. Do not print matching lines or secret values;
report only rule identifiers and sanitized file locators. A simple `git diff`
grep is not a complete secret check.

## Signing and timeout recovery

Use the repository's required signing mechanism and an appropriate timeout.
There is no universal signing duration. If signing fails or an operator prompt
expires, stop and offer to retry when the operator is present. Never disable
required signing or substitute an unsigned commit.

After a timeout, verify whether a commit was created and inspect index/worktree
state before retrying. Do not assume failure or blindly repeat a commit.

## Completion

Report the gates run, results, any operator-approved exceptions, staged scope,
commit signature verification and remaining blockers. Do not commit or push
without the operator's authorization.
