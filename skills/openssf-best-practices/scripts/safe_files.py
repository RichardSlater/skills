"""Bounded no-follow reads beneath a verified root, without target imports."""
from __future__ import annotations

import os
from pathlib import Path
import stat


def read_bytes(root: Path, relative: Path, limit: int) -> bytes:
    if (os.name != "posix" or not root.is_absolute() or relative.is_absolute()
            or ".." in relative.parts or ".." in root.parts or limit < 1):
        raise ValueError("safe reads require POSIX, an absolute root and a confined relative path")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    directory = os.open("/", flags | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in root.parts[1:]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        device = os.fstat(directory).st_dev
        for part in relative.parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
            if os.fstat(directory).st_dev != device:
                raise ValueError("cross-device traversal refused")
        descriptor = os.open(relative.name, flags, dir_fd=directory)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_dev != device or before.st_size > limit):
            raise ValueError("linked, special, cross-device or oversized input refused")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
        if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("input exceeded its limit or changed during inspection")
        return bytes(data)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)
