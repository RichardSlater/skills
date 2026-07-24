## ADDED Requirements

### Requirement: CodeQL analysis is a required status check for merging
The branch protection ruleset for `main` SHALL require successful CodeQL analysis before allowing merges. Both the `actions` and `python` language analyses SHALL be required.

#### Scenario: CodeQL must pass before merge (actions)
- **WHEN** a PR targets `main`
- **THEN** the `Analyze (actions)` CodeQL job must complete successfully before the PR can be merged

#### Scenario: CodeQL must pass before merge (python)
- **WHEN** a PR targets `main`
- **THEN** the `Analyze (python)` CodeQL job must complete successfully before the PR can be merged

#### Scenario: CodeQL failure blocks merge
- **WHEN** CodeQL detects a vulnerability or the job fails
- **THEN** the PR cannot be merged until the failure is resolved and the check passes

#### Scenario: CodeQL runs on all PRs and pushes
- **WHEN** a PR is created or code is pushed to `main`
- **THEN** CodeQL analysis is triggered for both `actions` and `python` languages

### Requirement: CodeQL configuration covers all relevant languages
The CodeQL configuration SHALL analyze Python and GitHub Actions workflows. The analysis SHALL run on PRs, pushes to `main`, and on a weekly schedule.

#### Scenario: CodeQL analyzes Python code
- **WHEN** CodeQL runs
- **THEN** it scans all Python files in the repository for security vulnerabilities

#### Scenario: CodeQL analyzes GitHub Actions workflows
- **WHEN** CodeQL runs
- **THEN** it scans all `.github/workflows/*.yml` files for workflow security issues

#### Scenario: CodeQL runs on schedule
- **WHEN** the weekly schedule triggers
- **THEN** CodeQL runs on the `main` branch to detect new vulnerabilities
