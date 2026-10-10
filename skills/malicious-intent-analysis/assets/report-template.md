# Artifact analysis: [target and verified identifier]

## Scope and conclusion

- **Review question and authorization:** [Requested target and allowed access.]
- **Provenance:** [Verified commit, version/digest, or transcript range; distinguish unverified claims.]
- **Reviewed material:** [Changed paths and relevant callers/configuration.]
- **Environment assumptions:** [Privileges, activation conditions, and ingestion paths.]
- **Collection:** [Files/bytes inspected, limits, target stability, and completeness.]
- **Bounded conclusion:** [Established behavior and impact; separate intent assessment.]

## Findings

Sort actionable findings by severity and then confidence. Put observations last.
Redact sensitive evidence and escape markup or control characters.

| ID | Severity | Evidence / locator | Mechanism and impact | Alternative / counterevidence | Confidence | Intent | Safe next step |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | [Category below] | [File/line, byte offset, or turn] | [Reachability, prerequisites, boundary, and harm] | [Strongest competing explanation] | [Level and basis] | [Assessment below] | [Minimum safe evidence or containment step] |

### Assessment scales

- **Critical:** Reachable catastrophic or broad compromise; state prerequisites.
- **High:** Substantial reachable harm, such as unauthorized sensitive access or execution.
- **Medium:** Meaningful harm with constrained scope or significant prerequisites.
- **Low:** Minor demonstrated harm; do not inflate uncertain signals into this category.
- **Observation:** Relevant behavior without established harm; not a safety verdict.

**Confidence:** High, Medium, or Low, with a concise evidence basis. Confidence
measures support for the mechanism and impact, not how severe the impact is.

**Intent:** Supported, Suspected, Inconclusive, Not supported by reviewed evidence,
or Not assessed. Supported requires evidence of deliberate harmful or
manipulative artifact behavior, not merely a harmful capability or an author's
identity. Not supported does not mean disproven.

## Mechanism details

For each substantive finding:

- **Trace:** [Entry -> activation -> source -> transformation -> boundary -> sink -> impact.]
- **Evidence status:** [Observed, inferred, unresolved, or unreachable links.]
- **Counterevidence:** [What limits or contradicts the claim.]
- **Unanswered question:** [Minimum discriminator and safe collection method.]

## Coverage and handoff

- Skipped files, unsupported formats, truncation, unavailable dependencies or source.
- Whether the target changed during inspection; unverified provenance or missing ingestion paths.
- Actions not performed: target execution, installation, endpoint contact, uploads, or remediation.
- Any proposed dynamic handoff, its required approval and containment, or incident response escalation.

**No substantiated findings in the reviewed material does not establish safety.**
