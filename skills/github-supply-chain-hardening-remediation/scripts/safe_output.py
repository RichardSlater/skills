"""No-follow, descriptor-relative atomic output helpers (POSIX only)."""
from __future__ import annotations

import os
from pathlib import Path, PurePath
import stat
import uuid


class UnsafePathError(ValueError):
    pass


def _relative(value: str | Path) -> PurePath:
    raw = str(value)
    path = PurePath(raw)
    if (not raw or raw in {".", "/"} or path.is_absolute() or ".." in path.parts
            or "\\" in raw or (len(raw) >= 2 and raw[1] == ":")):
        raise UnsafePathError("output must be a non-empty relative file path")
    return path


def _directory(parent: int, name: str, *, create: bool = False) -> int:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError as exc:
        raise UnsafePathError("output parent is missing, linked or not a directory") from exc


def atomic_write_text(root: Path, relative: str | Path, content: str, *,
                      allowed_subtrees: tuple[str, ...] | None = None) -> Path:
    """Replace a regular file using pinned directory descriptors, never resolve links."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not root.is_absolute():
        raise UnsafePathError("verified root must be absolute; POSIX no-follow access required")
    path = _relative(relative)
    if ".." in root.parts:
        raise UnsafePathError("root must not contain traversal")
    if allowed_subtrees and path.parts[0] not in allowed_subtrees:
        raise UnsafePathError("output is outside the approved subtree")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".bestpractices-" + uuid.uuid4().hex
    created = False
    try:
        for part in root.parts[1:]:
            child = _directory(directory, part)
            os.close(directory)
            directory = child
        for part in path.parts[:-1]:
            child = _directory(directory, part, create=True)
            os.close(directory)
            directory = child
        try:
            destination = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            destination = None
        if destination and (not stat.S_ISREG(destination.st_mode) or destination.st_nlink != 1):
            raise UnsafePathError("output destination must be an unlinked regular file")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        created = True
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        created = False
        os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)
    return root / path
