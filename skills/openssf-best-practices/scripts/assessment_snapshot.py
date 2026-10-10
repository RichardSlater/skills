#!/usr/bin/env python3
"""Content-based read-only assessment baseline (HEAD, index and visible files)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from safe_files import read_bytes
from safe_output import atomic_write_text


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                             "-C", str(root), *arguments], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ValueError("snapshot Git metadata unavailable")
    return result.stdout.strip() if "-z" not in arguments else result.stdout


def snapshot(root: Path) -> dict:
    root = Path(git(root, "rev-parse", "--show-toplevel")).absolute()
    try:
        head = git(root, "rev-parse", "--verify", "HEAD")
    except ValueError:
        head = None
    index = Path(git(root, "rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = root / index
    index_hash = hashlib.sha256(read_bytes(index.parent.absolute(), Path(index.name), 16 * 1024 * 1024)).hexdigest() if index.exists() else None
    paths = sorted(set(git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")) - {""})
    if len(paths) > 10000:
        raise ValueError("snapshot file budget exceeded")
    files = {}
    total = 0
    for relative in paths:
        path = root / relative
        try:
            info = path.lstat()
        except FileNotFoundError:
            files[relative] = {"type": "missing"}
            continue
        if stat.S_ISLNK(info.st_mode):
            data = os.readlink(path).encode()
            kind = "symlink"
        else:
            data = read_bytes(root, Path(relative), 16 * 1024 * 1024)
            kind = "regular"
        total += len(data)
        if total > 100 * 1024 * 1024:
            raise ValueError("snapshot byte budget exceeded")
        files[relative] = {"type": kind, "sha256": hashlib.sha256(data).hexdigest(), "mode": info.st_mode}
    return {"repository": str(root), "head": head, "index_sha256": index_hash, "files": files,
            "coverage": "tracked and non-ignored untracked files; ignored paths excluded"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "compare"))
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    try:
        current = snapshot(args.repository)
        if args.operation == "compare":
            if args.baseline is None:
                raise ValueError("comparison requires --baseline")
            previous = json.loads(args.baseline.read_text(encoding="utf-8"))
            if current != previous:
                raise ValueError("assessment changed HEAD, index or visible working-tree content")
            print("Assessment content unchanged within recorded coverage")
        else:
            if args.output is None or args.output.absolute().is_relative_to(Path(current["repository"])):
                raise ValueError("snapshot output must be outside the target repository")
            atomic_write_text(args.output.parent.absolute(), args.output.name,
                              json.dumps(current, sort_keys=True, indent=2) + "\n")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
