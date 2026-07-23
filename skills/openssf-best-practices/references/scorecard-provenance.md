# Scorecard artifact provenance

- **Upstream image:** `ghcr.io/ossf/scorecard`
- **Reviewed release tag:** `v5.5.0`
- **Immutable OCI index digest:** `sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795`
- **Verified:** 2026-07-23

The digest was resolved from the GitHub Container Registry manifest endpoint for `v5.5.0` using its anonymous pull token and OCI index media type. The runner uses the digest, never the mutable tag.

To update, review the upstream Scorecard release, resolve the new tag through GHCR, record the returned `Docker-Content-Digest`, update `scripts/scorecard_runner.py`, and review the diff.
