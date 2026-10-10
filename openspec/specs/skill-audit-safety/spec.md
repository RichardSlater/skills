# skill-audit-safety Specification

## Purpose

Define enforceable execution, evidence handling and correctness boundaries for independently installed repository security skills.

## Requirements

### Requirement: Constrained execution and filesystem access
Skill helpers SHALL bound execution, terminate child processes and containers on timeout, reject out-of-root or linked target reads/writes, and execute credential-bearing container images only by immutable digest after explicit approval.

#### Scenario: Timed-out execution
- **WHEN** a repository or Scorecard deadline expires
- **THEN** the helper terminates and joins started work, removes its container, and does not publish success evidence

### Requirement: Evidence and authority integrity
Skill helpers SHALL obtain repository/destination-specific consent before external enrichment, enforce approved output paths, distinguish unavailable evidence from findings, and report actual executor provenance.

#### Scenario: Local-only assessment
- **WHEN** no network consent is supplied
- **THEN** discovery inspects only local files and does not contact GitHub or BadgeApp

### Requirement: Correct analysis and documentation
Skills SHALL inspect parsed workflow steps and relevant manifests, preserve effective unrelated permissions, avoid emitting secrets, and document actual supported workflows.

#### Scenario: Typical workflow syntax
- **WHEN** a workflow uses sequence-form actions and multiline scripts
- **THEN** mutable references and untrusted interpolation are detected independently of formatting
