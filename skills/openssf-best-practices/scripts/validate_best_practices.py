#!/usr/bin/env python3
"""Validate and deterministically format a schema-backed BadgeApp proposal."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_output import atomic_write_text

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "schema" / "badgeapp-424f55a.json"
NON_CRITERION_FIELDS = {"name", "description", "license", "implementation_languages"}
URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(?:authorization\s*[:=]\s*bearer|api[_-]?key\s*[:=]|secret\s*[:=]|token\s*[:=])\s*[^\s]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
)


def unsafe_evidence_text(value: str) -> str | None:
    """Return a non-sensitive diagnostic for prohibited evidence text."""
    if any(pattern.search(value) for pattern in SECRET_PATTERNS):
        return "appears to contain a credential or private key"
    if re.search(r"(?i)(?:^|\s)(?:[A-Za-z]:[\\/]|\\\\|file:)", value):
        return "must not contain a local filesystem path"
    for raw_url in URL_PATTERN.findall(value):
        parsed = urlparse(raw_url.rstrip(".,;"))
        host = parsed.hostname
        if parsed.username or parsed.password or parsed.scheme != "https" or not host:
            return "contains an unsafe evidence URL"
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback or address.is_link_local:
                return "contains a private/local evidence URL"
        except ValueError:
            if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(".local"):
                return "contains a private/local evidence URL"
    return None


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("pinned BadgeApp schema is missing or corrupt") from exc
    if schema.get("schema_format_version") != 1 or not isinstance(schema.get("fields"), dict):
        raise ValueError("pinned BadgeApp schema version is unsupported")
    for name, metadata in schema["fields"].items():
        if not isinstance(name, str) or not isinstance(metadata, dict) or not metadata.get("section") or not metadata.get("levels"):
            raise ValueError("pinned BadgeApp schema has incomplete field metadata")
    return schema


def validate(data: Any, schema: dict[str, Any] | None = None, section: str | None = None) -> list[str]:
    schema = schema or load_schema()
    fields = schema["fields"]
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Top-level JSON value must be an object."]
    for key in sorted(data):
        value = data[key]
        if not isinstance(key, str):
            errors.append("Invalid non-string field name")
            continue
        if key.endswith("_status"):
            base = key[:-7]
            metadata = fields.get(base)
            if metadata is None:
                errors.append(f"{key}: unknown BadgeApp criterion")
                continue
            if section and section not in metadata["levels"]:
                errors.append(f"{key}: criterion does not belong to {section} section")
            allowed = metadata["status_values"]
            if not isinstance(value, str) or value not in {*allowed, "unknown"}:
                errors.append(f"{key}: expected one of {allowed}")
                continue
            # BadgeApp automation treats ? and unknown as unanswered, not claims.
            if value in {"?", "unknown"}:
                continue
            if value == "N/A" and not metadata.get("na_allowed", False):
                errors.append(f"{key}: N/A is not allowed by the pinned schema")
            justification = f"{base}_justification"
            if value in {"Met", "Unmet", "N/A"} and (
                metadata.get("met_justification_required", False) or
                (value == "N/A" and metadata.get("na_justification_required", False))
            ) and justification not in data:
                errors.append(f"{key}: missing required {justification}")
        elif key.endswith("_justification"):
            base = key[:-14]
            if base not in fields:
                errors.append(f"{key}: unknown BadgeApp criterion")
            elif not isinstance(value, str):
                errors.append(f"{key}: justification must be a string")
            elif f"{base}_status" not in data:
                errors.append(f"{key}: missing paired {base}_status")
            else:
                reason = unsafe_evidence_text(value)
                if reason:
                    errors.append(f"{key}: {reason}")
        elif key in NON_CRITERION_FIELDS:
            if not isinstance(value, str):
                errors.append(f"{key}: value must be a string")
            else:
                reason = unsafe_evidence_text(value)
                if reason:
                    errors.append(f"{key}: {reason}")
        else:
            errors.append(f"{key}: unknown BadgeApp field")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true", help="Do not rewrite; fail if formatting differs")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--section", choices=("passing", "silver", "gold"))
    args = parser.parse_args()
    try:
        schema = load_schema(args.schema)
        original = args.path.read_text(encoding="utf-8")
        data = json.loads(original)
        errors = validate(data, schema, args.section)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    formatted = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check and original != formatted:
        print("ERROR: file is valid but not deterministically formatted", file=sys.stderr)
        return 2
    if not args.check:
        atomic_write_text(args.path.parent.resolve(), args.path.name, formatted)
    print(f"Valid: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
