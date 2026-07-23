#!/usr/bin/env python3
"""Inspect GitHub CLI account context without exposing credential values."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from typing import Any

ACCOUNT_RE = re.compile(r"^\s*[✓X!]\s+Logged in to \S+ account (?P<login>\S+)")
ACTIVE_RE = re.compile(r"^\s*- Active account:\s*(?P<active>true|false)\s*$", re.IGNORECASE)
SCOPES_RE = re.compile(r"^\s*- Token scopes:\s*(?P<scopes>.+)$")
REPOSITORY_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+)$")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, shell=False)


def parse_status(output: str) -> list[dict[str, Any]]:
    """Parse the stable account/login lines while deliberately ignoring token lines."""
    accounts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in output.splitlines():
        match = ACCOUNT_RE.match(line)
        if match:
            current = {"login": match.group("login"), "active": False, "scopes": []}
            accounts.append(current)
            continue
        if current is None:
            continue
        match = ACTIVE_RE.match(line)
        if match:
            current["active"] = match.group("active").lower() == "true"
            continue
        match = SCOPES_RE.match(line)
        if match:
            current["scopes"] = re.findall(r"'([^']+)'", match.group("scopes"))
    return accounts


def account_inventory(hostname: str) -> list[dict[str, Any]]:
    result = run(["gh", "auth", "status", "--hostname", hostname])
    accounts = parse_status(result.stdout + "\n" + result.stderr)
    if result.returncode and not accounts:
        raise RuntimeError("unable to enumerate GitHub CLI accounts")
    return accounts


def viewer_permission(repository: str) -> tuple[str | None, str | None]:
    match = REPOSITORY_RE.fullmatch(repository)
    if not match:
        raise ValueError("repository must be owner/name")
    result = run([
        "gh", "api", "graphql",
        "-f", "query=query($owner:String!,$name:String!){repository(owner:$owner,name:$name){viewerPermission}}",
        "-F", f"owner={match.group('owner')}",
        "-F", f"name={match.group('name')}",
        "--jq", ".data.repository.viewerPermission",
    ])
    if result.returncode:
        return None, "unavailable"
    permission = result.stdout.strip()
    return (permission or None), None


def inspect(hostname: str, repository: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"hostname": hostname, "accounts": account_inventory(hostname)}
    active = next((account["login"] for account in result["accounts"] if account["active"]), None)
    result["active_account"] = active
    if repository:
        permission, error = viewer_permission(repository)
        result["repository"] = repository
        result["active_viewer_permission"] = permission
        if error:
            result["permission_evidence"] = error
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default="github.com")
    parser.add_argument("--repo", help="optional owner/name repository permission check")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.hostname, args.repo), indent=2, sort_keys=True))
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
