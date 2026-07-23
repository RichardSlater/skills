"""Symlink-safe, repository-confined atomic output helpers."""
from __future__ import annotations

import os
from pathlib import Path, PurePath
import stat
import tempfile


class UnsafePathError(ValueError):
    pass


def _relative(value: str | Path) -> PurePath:
    raw = str(value)
    path = PurePath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or any(not part for part in path.parts):
        raise UnsafePathError("output path must be a non-empty repository-relative path")
    # Windows absolute paths are not absolute on POSIX.
    if len(raw) >= 2 and raw[1] == ":" or raw.startswith("\\\\"):
        raise UnsafePathError("output path must not be a platform-specific absolute path")
    return path


def _not_symlink(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise UnsafePathError("output path contains a symbolic link")


def _safe_parent(root: Path, relative: PurePath, allowed_subtrees: tuple[str, ...] | None) -> tuple[Path, Path]:
    if not root.is_absolute():
        raise UnsafePathError("verified repository root must be absolute")
    _not_symlink(root)
    root = root.resolve(strict=True)
    if allowed_subtrees and relative.parts[0] not in allowed_subtrees:
        raise UnsafePathError("output path is outside the approved output subtree")
    parent = root
    for part in relative.parts[:-1]:
        candidate = parent / part
        _not_symlink(candidate)
        if not candidate.exists():
            candidate.mkdir(mode=0o700)
        _not_symlink(candidate)
        if not candidate.is_dir():
            raise UnsafePathError("output parent is not a directory")
        parent = candidate
    try:
        parent.resolve(strict=True).relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("output path escapes the verified repository root") from exc
    destination = parent / relative.name
    _not_symlink(destination)
    return parent, destination


def atomic_write_text(root: Path, relative: str | Path, content: str, *, allowed_subtrees: tuple[str, ...] | None = None) -> Path:
    """Atomically replace one regular file below a verified repository root."""
    relative_path = _relative(relative)
    parent, destination = _safe_parent(root, relative_path, allowed_subtrees)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".bestpractices-", dir=parent, text=True)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _not_symlink(destination)
        _safe_parent(root, relative_path, allowed_subtrees)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination
