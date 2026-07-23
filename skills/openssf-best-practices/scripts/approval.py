"""Bounded approval checks for the mutation phase of this skill."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any


class ApprovalError(ValueError):
    """An apply request is not covered by an explicit approval record."""


@dataclass(frozen=True)
class ApprovalRecord:
    repository: Path
    allowed_paths: frozenset[str]
    scope: str


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ApprovalError("approval contains an unsafe repository-relative path")
    return path.as_posix()


def load_approval(path: Path, repository: Path) -> ApprovalRecord:
    """Load an explicit, repository-scoped apply approval JSON record."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApprovalError("apply requires a valid approval record") from exc
    if not isinstance(raw, dict) or raw.get("scope") != "apply":
        raise ApprovalError("approval record must explicitly authorize apply scope")
    approved_repo = raw.get("repository")
    allowed_paths = raw.get("allowed_paths")
    if not isinstance(approved_repo, str) or not isinstance(allowed_paths, list):
        raise ApprovalError("approval record must name repository and allowed_paths")
    if Path(approved_repo).resolve() != repository.resolve():
        raise ApprovalError("approval record is for a different repository")
    if not allowed_paths or not all(isinstance(item, str) for item in allowed_paths):
        raise ApprovalError("approval record must list one or more allowed paths")
    return ApprovalRecord(repository.resolve(), frozenset(_relative_path(item) for item in allowed_paths), "apply")


def require_approved_path(record: ApprovalRecord, destination: str) -> None:
    if _relative_path(destination) not in record.allowed_paths:
        raise ApprovalError("destination is not listed in the approval record")


def require_clean_tree(repository: Path, allow_dirty: bool = False) -> None:
    result = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise ApprovalError("could not determine target repository status")
    if result.stdout and not allow_dirty:
        raise ApprovalError("target repository is dirty; explicitly authorize the listed existing changes")
