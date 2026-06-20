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
5. Open a pull request using the template and include validation evidence.

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
- [ ] Relevant commands were run, for example:

  ```bash
  python -m compileall skills/github-supply-chain-hardening-analysis/scripts
  ```

## Coding and documentation standards

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
