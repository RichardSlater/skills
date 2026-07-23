# BadgeApp schema provenance

- **Upstream:** `https://github.com/coreinfrastructure/best-practices-badge`
- **Immutable commit:** `424f55aff728c97d55a3df53b2d04deef3bcb0d9`
- **Source:** `criteria/criteria.yml`
- **Retrieved:** 2026-07-23
- **Schema format:** 1

`badgeapp-424f55a.json` is a reviewable, flattened representation of the official ordered criteria YAML. Each criterion records its section/eligible badge levels, accepted statuses, and `N/A`/justification requirements.

To update it, deliberately review a new immutable upstream commit, retrieve `criteria/criteria.yml` at that commit, regenerate the flattened schema with the same field mapping, update this provenance record, and review the resulting JSON diff. Never regenerate from an upstream default branch during an audit.
