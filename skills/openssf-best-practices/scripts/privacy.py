"""Consent gates for external disclosure of private repository identity."""
from __future__ import annotations
from typing import Any


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
