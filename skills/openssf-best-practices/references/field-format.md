# `.bestpractices.json` field format

Validation is driven by the pinned official BadgeApp schema at [`schema/badgeapp-424f55a.json`](schema/badgeapp-424f55a.json), whose source and update procedure are recorded in [`schema/PROVENANCE.md`](schema/PROVENANCE.md). Unknown fields, wrong-section fields, and unsupported `N/A` values are rejected.

Criterion answers use a criterion status plus an optional or schema-required justification:

```json
{
  "floss_license_status": "Met",
  "floss_license_justification": "Apache-2.0 license: https://github.com/OWNER/REPO/blob/main/LICENSE"
}
```

Exact status values are `Met`, `Unmet`, `N/A`, and `?`. `N/A` is valid only when the schema permits it. `?` is an unanswered value and does not claim compliance.

Proposal generation supports the official metal-series sections `passing`, `silver`, `gold`, and `choose`; it does not generate OSPS Baseline proposals. Every proposal records the schema version and upstream commit in its local assessment metadata.

Metadata fields supported by this helper are `name`, `description`, `license`, and `implementation_languages`.
