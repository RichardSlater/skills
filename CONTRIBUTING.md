# Contributing

Thank you for improving this skills repository.

## Before you start

- Check existing issues and pull requests to avoid duplicate work.
- For security vulnerabilities, follow [`SECURITY.md`](SECURITY.md) instead of opening a public issue.
- Keep changes small, focused, and easy to review.

## Development workflow

1. Fork or branch from the default branch.
2. Make the smallest safe change that solves the problem.
3. Update documentation when behavior, usage, or safety expectations change.
4. Run relevant validation before opening a pull request.
5. Add or update automated tests for behavior changes. Changes that cannot be tested automatically must explain why in the pull request.
6. Open a pull request using the template and include validation evidence.

## Conventional Commit and squash-merge policy

Pull requests must have a Conventional Commit title because the canonical squash
commit on `main` is the release input. Use `type(scope optional)!: description`.
`fix` creates a patch release, `feat` creates a minor release, and `!` or a
`BREAKING CHANGE:` footer creates a major release. Examples:

- `fix(parser): handle an empty manifest`
- `feat(skills): add a validator`
- `feat!: remove the legacy configuration`

Other valid types (`build`, `chore`, `ci`, `docs`, `refactor`, `style`, and
`test`) do not independently release. Use squash merging so the checked pull
request title becomes the commit message on `main`.

## Validation commands

Install the system-managed [pre-commit](https://pre-commit.com/) command, then
install the repository hooks once:

```bash
pre-commit install
```

Run the complete local quality gate before opening a pull request:

```bash
pre-commit run --all-files
python -m compileall -q skills
python -m unittest discover -s skills/github-supply-chain-hardening-remediation/tests -v
python -m coverage run --rcfile=tests/.coveragerc -m unittest discover -s tests/openssf_best_practices -v
python -m coverage report --rcfile=tests/.coveragerc
```

The `Validate Skills` workflow runs the same pre-commit checks, compilation,
linting, unit tests, and scoped coverage check for every pull request and every
commit to `main`. The coverage report is configured to fail below 85%. Major new
functionality **must** include automated tests. Bug fixes must include regression
tests where practical; reviewers should not merge known test, coverage, or lint
failures.

## Validation checklist

For skill-instruction changes:

- [ ] The skill purpose and trigger conditions are clear.
- [ ] Required inputs are documented.
- [ ] Safety constraints are explicit.
- [ ] Failure handling is documented.
- [ ] User-facing output expectations are clear.

For Python script changes:

- [ ] The script does not print token values or secrets.
- [ ] Authentication uses local environment/CLI mechanisms rather than pasted secrets.
- [ ] Error messages are actionable and do not expose sensitive data.
- [ ] Repository-scale work remains inside scripts rather than agent context.
- [ ] The repository validation commands above pass.

## Coding and documentation standards

Python contributions must follow the repository's Ruff linting rules; the
pre-commit hooks enforce those rules. Markdown, YAML, and whitespace checks are
also enforced before commit and again in GitHub Actions.
Document any rare style exception adjacent to the relevant code so it can be
reviewed.

- Prefer explicit, readable code over cleverness.
- Use least-privilege defaults for GitHub permissions and tokens.
- Avoid destructive behavior unless the skill explicitly requires it and the user has approved it.
- Keep generated files deterministic where possible.
- Write Markdown that is useful to both humans and agent tooling.

## Pull request expectations

A good pull request includes:

- A clear summary of what changed.
- Why the change is needed.
- Commands run and their results.
- Screenshots or sample output when documentation/output behavior changes.
- Security considerations for changes that touch credentials, GitHub APIs, shell commands, workflows, or repository mutation.

## Maintainer review

Maintainers may ask for changes to reduce scope, improve safety, add validation, or clarify documentation. Please keep discussions respectful and focused on the project.
