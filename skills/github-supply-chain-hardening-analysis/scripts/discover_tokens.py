#!/usr/bin/env python3
"""Discover usable GitHub tokens without printing token values.

Token sources checked:
- GITHUB_TOKEN environment variable
- `gh auth token` for the active GitHub CLI account

The script keeps token bytes in process memory only. Output contains only metadata
returned by GitHub APIs plus a short non-secret token identifier derived from a
SHA-256 digest so operators can distinguish discovered tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API_ROOT = "https://api.github.com"
USER_AGENT = "github-supply-chain-hardening-token-discovery"


@dataclass(frozen=True)
class TokenCandidate:
    source: str
    token: str

    @property
    def token_id(self) -> str:
        return hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:12]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover GitHub token account/org/permission metadata without printing tokens")
    parser.add_argument("--json", action="store_true", help="Emit JSON only (default also emits JSON)")
    parser.add_argument("--repo-sample-limit", type=int, default=100, help="Maximum repositories to inspect for permission summary")
    return parser.parse_args(argv)


def _clean_token(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value or None


def _token_candidates() -> list[TokenCandidate]:
    candidates: list[TokenCandidate] = []
    env_token = _clean_token(os.environ.get("GITHUB_TOKEN"))
    if env_token:
        candidates.append(TokenCandidate("GITHUB_TOKEN", env_token))

    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        completed = None
    if completed and completed.returncode == 0:
        gh_token = _clean_token(completed.stdout)
        if gh_token:
            candidates.append(TokenCandidate("gh auth token", gh_token))

    deduped: list[TokenCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        digest = candidate.token_id
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append(candidate)
    return deduped


def _request(token: str, path: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, str], Any]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(
        f"{API_ROOT}{path}{query}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else None
            return response.status, dict(response.headers.items()), data
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {"message": exc.reason}
        except json.JSONDecodeError:
            data = {"message": exc.reason}
        return exc.code, dict(exc.headers.items()), data


def _get_all_pages(token: str, path: str, params: dict[str, Any] | None = None, max_pages: int = 10) -> tuple[list[Any], dict[str, str], int | None]:
    items: list[Any] = []
    first_headers: dict[str, str] = {}
    final_status: int | None = None
    page = 1
    while page <= max_pages:
        page_params = dict(params or {})
        page_params.setdefault("per_page", 100)
        page_params["page"] = page
        status, headers, data = _request(token, path, page_params)
        final_status = status
        if page == 1:
            first_headers = headers
        if status >= 400:
            break
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < int(page_params["per_page"]):
            break
        page += 1
    return items, first_headers, final_status


def _scope_list(headers: dict[str, str], name: str) -> list[str]:
    raw = headers.get(name) or headers.get(name.lower()) or ""
    return sorted([part.strip() for part in raw.split(",") if part.strip()])


def _repo_permission_summary(repos: list[dict[str, Any]]) -> dict[str, Any]:
    visibility: dict[str, int] = {}
    permissions = {"admin": 0, "maintain": 0, "push": 0, "triage": 0, "pull": 0}
    owners: dict[str, int] = {}
    archived = 0
    for repo in repos:
        visibility[str(repo.get("visibility") or ("private" if repo.get("private") else "public"))] = visibility.get(str(repo.get("visibility") or ("private" if repo.get("private") else "public")), 0) + 1
        if repo.get("archived"):
            archived += 1
        owner = ((repo.get("owner") or {}).get("login")) or "unknown"
        owners[owner] = owners.get(owner, 0) + 1
        repo_permissions = repo.get("permissions") or {}
        for key in permissions:
            if repo_permissions.get(key):
                permissions[key] += 1
    return {
        "sampled_repositories": len(repos),
        "archived_in_sample": archived,
        "visibility_counts": dict(sorted(visibility.items())),
        "owner_counts": dict(sorted(owners.items())),
        "permission_counts": permissions,
    }


def inspect_token(candidate: TokenCandidate, repo_sample_limit: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": candidate.source,
        "token_id": candidate.token_id,
        "valid": False,
    }

    status, headers, user = _request(candidate.token, "/user")
    result["rate_limit_remaining"] = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
    result["oauth_scopes"] = _scope_list(headers, "X-OAuth-Scopes")
    result["accepted_oauth_scopes_for_user_endpoint"] = _scope_list(headers, "X-Accepted-OAuth-Scopes")
    if status >= 400:
        result["error"] = f"GitHub API returned HTTP {status} for /user"
        if isinstance(user, dict) and user.get("message"):
            result["error_message"] = user.get("message")
        return result

    result["valid"] = True
    result["account"] = {
        "login": user.get("login"),
        "id": user.get("id"),
        "type": user.get("type"),
        "name": user.get("name"),
    }

    orgs, _, org_status = _get_all_pages(candidate.token, "/user/orgs", max_pages=10)
    result["orgs"] = [
        {"login": org.get("login"), "id": org.get("id"), "description": org.get("description")}
        for org in orgs
        if isinstance(org, dict)
    ]
    if org_status and org_status >= 400:
        result["orgs_error"] = f"GitHub API returned HTTP {org_status} for /user/orgs"

    memberships, _, membership_status = _get_all_pages(candidate.token, "/user/memberships/orgs", max_pages=10)
    if membership_status and membership_status < 400:
        result["org_memberships"] = [
            {
                "org": ((membership.get("organization") or {}).get("login")),
                "state": membership.get("state"),
                "role": membership.get("role"),
            }
            for membership in memberships
            if isinstance(membership, dict)
        ]

    repos, _, repo_status = _get_all_pages(
        candidate.token,
        "/user/repos",
        params={"affiliation": "owner,collaborator,organization_member", "sort": "updated", "direction": "desc"},
        max_pages=max(1, (repo_sample_limit + 99) // 100),
    )
    repos = repos[:repo_sample_limit]
    if repo_status and repo_status < 400:
        result["repository_access_summary"] = _repo_permission_summary([repo for repo in repos if isinstance(repo, dict)])
    else:
        result["repository_access_error"] = f"GitHub API returned HTTP {repo_status} for /user/repos"

    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidates = _token_candidates()
    output: dict[str, Any] = {
        "tokens_discovered": len(candidates),
        "token_sources_checked": ["GITHUB_TOKEN", "gh auth token"],
        "tokens": [inspect_token(candidate, args.repo_sample_limit) for candidate in candidates],
        "security_note": "Token values are never printed; token_id is a short SHA-256 digest prefix for distinguishing tokens only.",
    }
    print(json.dumps(output, indent=2, sort_keys=True), flush=True)
    return 0 if candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
