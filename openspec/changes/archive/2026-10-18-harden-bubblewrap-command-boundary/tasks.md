## 1. Host Git boundary

- [x] 1.1 Run listed `git commit` and `git push` with only a project-scrubbed `PATH`, the real `HOME`, `USER`, and, for `git push`, an existing `SSH_AUTH_SOCK`
- [x] 1.2 Re-check hooks and `core.hooksPath` in that cleaned environment, and refuse host execution when `git config --local --get core.sshCommand` succeeds
- [x] 1.3 Add contract tests for inherited `GIT_DIR`, inherited `GIT_SSH_COMMAND`, and a repository `core.sshCommand`

## 2. Project and config boundary

- [x] 2.1 Refuse a project root that is the real home or an ancestor of it
- [x] 2.2 Refuse a project that contains a credential directory or the operator config, and mask `.env`, `.env.*`, and `.envrc` at any depth
- [x] 2.3 Fail closed when the hardlink walk exits non-zero
- [x] 2.4 Refuse a group- or other-writable, or wrongly owned, operator config directory or list file without creating or chmodding it
- [x] 2.5 Add contract tests for the home-root refusal, nested env files, in-project `.ssh`, a failed walk, and group-writable config

## 3. Extra-command and network parsing

- [x] 3.1 Treat an ELF extra command as `not available` unless `readelf` produces a usable dynamic-section report, allowing only an explicit static-ELF report
- [x] 3.2 Canonicalize resolver files, refuse home and non-`/etc`/`/run` targets, and content-copy allowed stubs without mounting their parents
- [x] 3.3 Bind certificate directories only when their canonical path stays under `/etc`
- [x] 3.4 Add contract tests for an unparsed ELF, a resolver path under the home directory, and a `/run` resolver stub

## 4. Skill description

- [x] 4.1 State in the skill description that network is off unless the command matches `network-commands`
- [x] 4.2 Assert that description in the skill contract test
