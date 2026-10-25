#!/usr/bin/python3
"""Read bubblewrap-isolation config.yml and emit applicable grants.

The launcher invokes this with /usr/bin/python3. It is not a host-command grant.
"""

from __future__ import annotations

import os
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("error: PyYAML is required to read config.yml\n")
    raise SystemExit(69)

GRANT_KEYS = ("extra", "network", "host", "package_managers")
LABELS = {
    "extra": "extra-commands",
    "network": "network-commands",
    "host": "host-commands",
    "package_managers": "package-managers",
}
KINDS = {
    "extra": "extra",
    "network": "network",
    "host": "host",
    "package_managers": "package",
}
MAX_BYTES = 262144


def die(message: str, status: int = 65) -> None:
    sys.stderr.write(f"error: {message}\n")
    raise SystemExit(status)


def string_list(value, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        die(f"config {label} must be a list of strings")
    checked = []
    for item in value:
        if item == "" or "\n" in item or "\r" in item or "\t" in item:
            die(f"unknown line in {LABELS[label]}: {item}")
        checked.append(item)
    return checked


def canonical_path(path) -> str:
    if not isinstance(path, str) or path == "" or "\n" in path or "\r" in path:
        die(f"config path is not canonical: {path}")
    if not path.startswith("/") or os.path.realpath(path) != path:
        die(f"config path is not canonical: {path}")
    return path


def emit(scope: str, section: dict) -> None:
    for key in GRANT_KEYS:
        if key not in section:
            continue
        for item in string_list(section[key], key):
            sys.stdout.write(f"{scope}\t{KINDS[key]}\t{item}\n")


def main() -> None:
    if len(sys.argv) != 3:
        die("config parser usage")
    config_path, project = sys.argv[1:]
    if not project.startswith("/") or os.path.realpath(project) != project:
        die(f"config path is not canonical: {project}")
    try:
        size = os.path.getsize(config_path)
    except OSError as exc:
        die(f"cannot read config.yml: {exc}")
    if size > MAX_BYTES:
        die("config.yml is too large")
    try:
        with open(config_path, encoding="utf-8") as handle:
            documents = list(yaml.safe_load_all(handle))
    except yaml.YAMLError as exc:
        die(f"invalid config.yml: {exc}")
    except OSError as exc:
        die(f"cannot read config.yml: {exc}")
    if not documents:
        return
    if len(documents) != 1:
        die("config.yml must contain one document")
    data = documents[0]
    if data is None:
        return
    if not isinstance(data, dict):
        die("config.yml must be a mapping")
    unknown = set(data) - {"global", "projects"}
    if unknown:
        die(f"unknown config key: {min(unknown)}")
    global_section = data.get("global")
    if global_section is None:
        global_section = {}
    if not isinstance(global_section, dict):
        die("config global must be a mapping")
    unknown = set(global_section) - set(GRANT_KEYS)
    if unknown:
        die(f"unknown config key: {min(unknown)}")
    projects = data.get("projects")
    if projects is None:
        projects = []
    if not isinstance(projects, list):
        die("config projects must be a list")
    parsed = []
    seen = set()
    for entry in projects:
        if not isinstance(entry, dict):
            die("config project entry must be a mapping")
        unknown = set(entry) - {"path", *GRANT_KEYS}
        if unknown:
            die(f"unknown config key: {min(unknown)}")
        if "path" not in entry:
            die("config project entry missing path")
        path = canonical_path(entry["path"])
        if path in seen:
            die(f"duplicate project path: {path}")
        seen.add(path)
        parsed.append((path, entry))
    emit("use", global_section)
    for path, entry in parsed:
        emit("use" if path == project else "skip", entry)


if __name__ == "__main__":
    main()
