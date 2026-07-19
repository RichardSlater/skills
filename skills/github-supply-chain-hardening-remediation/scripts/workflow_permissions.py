#!/usr/bin/env python3
"""Safely enforce permissions needed by Scorecard and SARIF workflows.

This deliberately edits only ``permissions`` mappings.  It does not serialize the
whole workflow, so action pins and their version comments survive unchanged.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

REQUIRED_BASELINE = {"contents": "read"}


def _load(text: str) -> dict[str, Any]:
    try:
        document = yaml.load(text, Loader=yaml.BaseLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid workflow YAML: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
        raise ValueError("workflow must contain a jobs mapping")
    return document


def _steps(job: Any) -> list[Any]:
    return job.get("steps", []) if isinstance(job, dict) and isinstance(job.get("steps"), list) else []


def _has_action(job: Any, action: str) -> bool:
    return any(isinstance(step, dict) and action in str(step.get("uses", "")).lower() for step in _steps(job))


def _is_true(value: Any) -> bool:
    return str(value).lower() == "true"


def scorecard_requirements(document: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return required permissions by Scorecard/SARIF-producing job.

    Scorecard jobs always need contents to checkout and inspect the repository.
    A job uploading SARIF needs security-events; publishing Scorecard results
    needs id-token.  SARIF jobs outside Scorecard are included as well because
    the same GitHub permission rule applies to CodeQL and other producers.
    """
    required: dict[str, dict[str, str]] = {}
    for name, job in document["jobs"].items():
        scorecard = _has_action(job, "ossf/scorecard-action")
        # CodeQL is the common case, but other actions named upload-sarif need
        # the same security-events permission.
        sarif = _has_action(job, "upload-sarif")
        if scorecard or sarif:
            permissions: dict[str, str] = {"contents": "read"}
            if sarif:
                permissions["security-events"] = "write"
            if scorecard:
                for step in _steps(job):
                    if isinstance(step, dict) and "ossf/scorecard-action" in str(step.get("uses", "")).lower():
                        publish = step.get("with", {}).get("publish_results") if isinstance(step.get("with"), dict) else None
                        if _is_true(publish):
                            permissions["id-token"] = "write"
            required[str(name)] = permissions
    return required


def validate_scorecard_workflow(text: str) -> list[str]:
    """Return semantic permission errors for Scorecard and SARIF jobs."""
    document = _load(text)
    errors: list[str] = []
    for name, required in scorecard_requirements(document).items():
        job = document["jobs"][name]
        actual = job.get("permissions", {}) if isinstance(job, dict) else {}
        if not isinstance(actual, dict):
            errors.append(f"jobs.{name}.permissions must be a mapping")
            continue
        for permission, value in required.items():
            if str(actual.get(permission, "")).lower() != value:
                errors.append(f"jobs.{name} requires {permission}: {value}")
    return errors


def _block_end(lines: list[str], start: int, indent: int) -> int:
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            break
        end += 1
    return end


def _find_key(lines: list[str], key: str, start: int, end: int, indent: int) -> int | None:
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:(?:\s|$)")
    for index in range(start, end):
        if pattern.match(lines[index]):
            return index
    return None


def _merge_permissions(lines: list[str], start: int, end: int, indent: int, required: dict[str, str]) -> list[str]:
    """Merge keys into a mapping, replacing only the unsafe read-all scalar."""
    key = _find_key(lines, "permissions", start, end, indent)
    if key is None:
        addition = [" " * indent + "permissions:\n", *[" " * (indent + 2) + f"{k}: {v}\n" for k, v in required.items()]]
        return lines[:start] + addition + lines[start:]
    value = lines[key].split(":", 1)[1].strip().split("#", 1)[0].strip()
    if value:
        if value != "read-all":
            raise ValueError(f"ambiguous scalar permissions at line {key + 1}: {value}")
        replacement = [" " * indent + "permissions:\n", *[" " * (indent + 2) + f"{k}: {v}\n" for k, v in required.items()]]
        return lines[:key] + replacement + lines[key + 1:]
    mapping_end = _block_end(lines, key, indent)
    existing: dict[str, int] = {}
    for index in range(key + 1, mapping_end):
        match = re.match(r"^\s+([\w-]+):", lines[index])
        if match:
            existing[match.group(1)] = index
    # A present but insufficient value (for example security-events: read) is
    # not a mergeable permission: change that key only, retaining its comment.
    for permission, value in required.items():
        if permission in existing:
            index = existing[permission]
            match = re.match(rf"^(\s*{re.escape(permission)}:)", lines[index])
            if match:
                comment = ""
                if "#" in lines[index]:
                    comment = " #" + lines[index].split("#", 1)[1]
                elif lines[index].endswith("\n"):
                    comment = "\n"
                lines[index] = f"{match.group(1)} {value}{comment}"
    additions = [" " * (indent + 2) + f"{k}: {v}\n" for k, v in required.items() if k not in existing]
    return lines[:mapping_end] + additions + lines[mapping_end:]


def remediate_workflow(text: str) -> str:
    """Add only missing required permissions, preserving unrelated job scopes."""
    document = _load(text)
    required_jobs = scorecard_requirements(document)
    if not required_jobs:
        return text
    lines = text.splitlines(keepends=True)
    # A read-only workflow baseline; job mappings below deliberately replace it.
    lines = _merge_permissions(lines, 0, len(lines), 0, REQUIRED_BASELINE)
    for job_name, required in required_jobs.items():
        # Reparse boundaries after every insertion rather than relying on stale indexes.
        jobs_index = _find_key(lines, "jobs", 0, len(lines), 0)
        assert jobs_index is not None
        jobs_end = _block_end(lines, jobs_index, 0)
        job_index = _find_key(lines, job_name, jobs_index + 1, jobs_end, 2)
        if job_index is None:
            raise ValueError(f"could not locate jobs.{job_name} for remediation")
        job_end = _block_end(lines, job_index, 2)
        lines = _merge_permissions(lines, job_index + 1, job_end, 4, required)
    output = "".join(lines)
    errors = validate_scorecard_workflow(output)
    if errors:
        raise ValueError("remediation did not satisfy validator: " + "; ".join(errors))
    return output


def scorecard_workflow_template() -> str:
    """The pinned default Scorecard workflow used when no workflow exists."""
    return """name: Scorecard supply-chain security\n\non:\n  branch_protection_rule:\n  schedule:\n    - cron: '17 14 * * 1'\n  push:\n    branches: [main]\n\npermissions:\n  contents: read\n\njobs:\n  analysis:\n    permissions:\n      contents: read\n      security-events: write\n      id-token: write\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2\n        with:\n          persist-credentials: false\n      - uses: ossf/scorecard-action@0864cf19026789058feabb7e87baa5f140aac736 # v2.3.3\n        with:\n          results_file: results.sarif\n          results_format: sarif\n          publish_results: true\n      - uses: github/codeql-action/upload-sarif@ddf5ce7296213f5548c91e2dd19df2d77d2b2d66 # v3\n        with:\n          sarif_file: results.sarif\n"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or remediate Scorecard/SARIF workflow permissions")
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--check", action="store_true", help="only validate; do not modify")
    args = parser.parse_args()
    source = args.workflow.read_text(encoding="utf-8")
    if args.check:
        errors = validate_scorecard_workflow(source)
        if errors:
            print("\n".join(errors))
            return 1
        return 0
    updated = remediate_workflow(source)
    if updated != source:
        args.workflow.write_text(updated, encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
