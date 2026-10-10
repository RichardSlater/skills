"""Consent gates for external disclosure of private repository identity."""
from __future__ import annotations
from typing import Any
import json
from pathlib import Path
import re


class PrivacyError(ValueError):
    pass


def disclosure_record(metadata: dict[str, Any], destination: str, consent: str | None) -> dict[str, str] | None:
    """Return scoped consent metadata or refuse private identity disclosure."""
    if not metadata.get("isPrivate", False):
        return None
    if consent != destination:
        raise PrivacyError(
            f"private repository assessment is local-only; explicitly consent to disclosure to {destination}"
        )
    return {"destination": destination, "scope": "current-repository-assessment"}


def require_disclosure(path: Path | None, repository: str, destination: str) -> dict[str, Any]:
    """Check an operator-supplied record, never infer consent from credentials."""
    if path is None or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise PrivacyError("external assessment requires repository/destination-bound consent")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrivacyError("invalid disclosure approval record") from exc
    if (not isinstance(record, dict) or not isinstance(record.get("repository"), str)
            or record["repository"].lower() != repository.lower()
            or not isinstance(record.get("destinations"), list)
            or not all(isinstance(item, str) and item in {"github", "bestpractices.dev", "scorecard"}
                       for item in record["destinations"])
            or destination not in record["destinations"]
            or record.get("scope") != "assessment-disclosure"):
        raise PrivacyError("approval does not cover this repository and destination")
    return {"repository": repository, "destination": destination, "scope": record["scope"]}
