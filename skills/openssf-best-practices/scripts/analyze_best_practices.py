#!/usr/bin/env python3
"""Small, token-efficient helpers for the OpenSSF Best Practices skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_output import atomic_write_text
from privacy import PrivacyError, disclosure_record
from validate_best_practices import load_schema, validate

BASE = "https://www.bestpractices.dev"
PROJECT_PATTERN = re.compile(
    r"(?:www\.)?bestpractices\.dev/(?:en/)?projects/(\d+)(?:/|['\"?#)\s]|$)",
    re.IGNORECASE,
)
TEXT_SUFFIXES = {".md", ".markdown", ".rst", ".adoc", ".asciidoc", ".html", ".htm"}
MIN_PYTHON_VERSION = (3, 11)
MAX_PROPOSAL_URL_LENGTH = 8_000
MAX_SCAN_FILES = 200
MAX_SCAN_FILE_BYTES = 256 * 1024
MAX_SCAN_TOTAL_BYTES = 2 * 1024 * 1024
MAX_SCAN_SECONDS = 5.0


def run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, check=False, shell=False, timeout=timeout
    )


def repo_metadata() -> dict[str, Any]:
    result = run([
        "gh", "repo", "view",
        "--json", "nameWithOwner,url,defaultBranchRef,isPrivate,isArchived,isFork"
    ])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh repo view failed")
    return json.loads(result.stdout)


def assessment_output_is_ignored(repository: Path, relative_output: Path) -> bool:
    """Use Git's ignore rules before allowing assessment output in a repository."""
    if relative_output.is_absolute() or ".." in relative_output.parts:
        return False
    result = run(["git", "-C", str(repository), "check-ignore", "--quiet", "--", str(relative_output)])
    return result.returncode == 0


def tracked_text_files() -> list[Path]:
    result = run(["git", "ls-files", "-z"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [Path(raw) for raw in result.stdout.split("\0") if raw and (Path(raw).name.lower().startswith("readme") or Path(raw).suffix.lower() in TEXT_SUFFIXES)]


def scan_project_ids(paths: list[Path], *, root: Path | None = None, clock=time.monotonic) -> tuple[set[int], list[dict[str, Any]], dict[str, Any]]:
    """Bounded, non-symlink documentation scan with completeness metadata."""
    root = root or Path.cwd(); started = clock(); ids: set[int] = set(); evidence: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {"files_considered": len(paths), "files_scanned": 0, "bytes_read": 0, "skipped": {}, "limits_hit": False}
    for path in paths:
        if metadata["files_scanned"] >= MAX_SCAN_FILES or clock() - started >= MAX_SCAN_SECONDS:
            metadata["limits_hit"] = True; break
        full = root / path
        try:
            stat_result = full.lstat()
        except OSError:
            metadata["skipped"]["unreadable"] = metadata["skipped"].get("unreadable", 0) + 1; continue
        if full.is_symlink():
            metadata["skipped"]["symlink"] = metadata["skipped"].get("symlink", 0) + 1; continue
        if stat_result.st_size > MAX_SCAN_FILE_BYTES:
            metadata["skipped"]["oversized"] = metadata["skipped"].get("oversized", 0) + 1; continue
        remaining_bytes = MAX_SCAN_TOTAL_BYTES - metadata["bytes_read"]
        if remaining_bytes <= 0:
            metadata["limits_hit"] = True; break
        try:
            with full.open("rb") as stream: raw = stream.read(remaining_bytes + 1)
        except OSError:
            metadata["skipped"]["unreadable"] = metadata["skipped"].get("unreadable", 0) + 1; continue
        if len(raw) > remaining_bytes:
            metadata["limits_hit"] = True; break
        metadata["bytes_read"] += len(raw); metadata["files_scanned"] += 1
        text = raw.decode("utf-8", errors="replace")
        for match in PROJECT_PATTERN.finditer(text):
            project_id = int(match.group(1)); ids.add(project_id); evidence.append({"source": str(path), "project_id": project_id, "match": match.group(0)[:200]})
    return ids, evidence, metadata


def normalize_github_repo_url(value: str) -> tuple[str, str, str]:
    """Return canonical GitHub host/owner/repository or reject an unsafe URL."""
    if not isinstance(value, str) or not value:
        raise ValueError("repository URL is missing or malformed")
    ssh = re.fullmatch(r"(?:ssh://)?git@([^/:]+)[:/]([^/]+)/([^/]+)", value.rstrip("/"))
    if ssh:
        host, owner, repository = ssh.groups()
    else:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("repository URL must be a credential-free GitHub HTTPS or SSH URL")
        host = parsed.hostname or ""
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError("repository URL must include GitHub owner and repository")
        owner, repository = parts
    if host.lower() != "github.com" or not owner or not repository:
        raise ValueError("repository URL must identify a github.com owner and repository")
    repository = repository.removesuffix(".git")
    if not repository:
        raise ValueError("repository URL must include a repository name")
    return ("github.com", owner.lower(), repository.lower())


def verify_project_candidates(
    candidate_ids: set[int], target_repo_url: str
) -> tuple[list[int], list[dict[str, Any]]]:
    """Fetch and identity-check every discovered BadgeApp project candidate."""
    target = normalize_github_repo_url(target_repo_url)
    verified: list[int] = []
    rejected: list[dict[str, Any]] = []
    for project_id in sorted(candidate_ids):
        try:
            project = fetch_project(project_id)
            candidate = normalize_github_repo_url(project.get("repo_url", ""))
            if candidate != target:
                raise ValueError("candidate repository does not match target identity")
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            rejected.append({"project_id": project_id, "reason": str(exc)})
        else:
            verified.append(project_id)
    return verified, rejected


def discover_ids(private_consent: str | None = None) -> dict[str, Any]:
    meta = repo_metadata()
    consent = (
        disclosure_record(meta, "bestpractices.dev", private_consent)
        if meta.get("isPrivate", False) and private_consent
        else None
    )
    ids, evidence, scan = scan_project_ids(tracked_text_files())

    for proposal in (Path(".bestpractices.json"), Path(".project.d/bestpractices.json")):
        if proposal.exists():
            evidence.append({
                "source": str(proposal),
                "project_id": None,
                "match": "automation proposal file exists; this alone does not prove enrolment",
            })

    lookup: dict[str, Any] = {"status": "not_requested"}
    if not meta.get("isPrivate", False) or consent:
        lookup = lookup_redirect(meta["url"])
        if lookup.get("project_id"):
            ids.add(int(lookup["project_id"]))
            evidence.append({
                "source": "bestpractices.dev URL lookup",
                "project_id": int(lookup["project_id"]),
                "match": lookup.get("location"),
            })

    verified_ids: list[int] = []
    rejected_candidates: list[dict[str, Any]] = []
    if not meta.get("isPrivate", False) or consent:
        verified_ids, rejected_candidates = verify_project_candidates(ids, meta["url"])
    return {
        "repository": meta,
        "project_ids": verified_ids,
        "enrolment": (
            "indeterminate" if scan["limits_hit"]
            else "identified" if len(verified_ids) == 1
            else "ambiguous" if len(verified_ids) > 1
            else "not-identified"
        ),
        "evidence": evidence,
        "scan": scan,
        "rejected_candidates": rejected_candidates,
        "lookup": lookup,
        "private_disclosure_consent": consent,
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def lookup_redirect(repo_url: str) -> dict[str, Any]:
    query = urlencode({"as": "edit", "url": repo_url, "section": "choose"})
    url = f"{BASE}/projects?{query}"
    opener = build_opener(NoRedirect)
    request = Request(url, headers={"User-Agent": "openssf-best-practices-skill/1"})
    try:
        response = opener.open(request, timeout=20)
        location = response.headers.get("Location")
        status = response.status
    except HTTPError as exc:
        location = exc.headers.get("Location")
        status = exc.code
    except (URLError, OSError) as exc:
        return {"status": "failed", "error": str(exc), "url": url}

    project_id = None
    if location:
        match = PROJECT_PATTERN.search(location)
        if match:
            project_id = int(match.group(1))
    return {
        "status": status,
        "location": location,
        "project_id": project_id,
        "url": url,
    }


def fetch_project(project_id: int) -> dict[str, Any]:
    url = f"{BASE}/projects/{project_id}.json"
    request = Request(url, headers={"User-Agent": "openssf-best-practices-skill/1"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def scorecard_summary(data: dict[str, Any]) -> dict[str, Any]:
    checks = data.get("checks", [])
    compact = []
    for check in checks:
        compact.append({
            "name": check.get("name"),
            "score": check.get("score"),
            "reason": check.get("reason"),
        })
    return {
        "score": data.get("score"),
        "date": data.get("date"),
        "repo": data.get("repo"),
        "checks": compact,
    }


def validate_project_response(data: Any, expected_repo_url: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("id"), int) or not isinstance(data.get("repo_url"), str):
        raise ValueError("project response is missing required identity fields")
    normalize_github_repo_url(data["repo_url"])
    if expected_repo_url and normalize_github_repo_url(data["repo_url"]) != normalize_github_repo_url(expected_repo_url):
        raise ValueError("project response repository does not match target identity")
    return data


def project_summary(data: dict[str, Any]) -> dict[str, Any]:
    data = validate_project_response(data)
    status_fields = {
        key: value for key, value in data.items()
        if isinstance(key, str) and key.endswith("_status")
    }
    counts: dict[str, int] = {}
    for value in status_fields.values():
        label = str(value)
        counts[label] = counts.get(label, 0) + 1
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "repo_url": data.get("repo_url"),
        "homepage_url": data.get("homepage_url"),
        "badge_percentage_0": data.get("badge_percentage_0"),
        "badge_percentage_1": data.get("badge_percentage_1"),
        "badge_percentage_2": data.get("badge_percentage_2"),
        "tiered_percentage": data.get("tiered_percentage"),
        "badge_level": data.get("badge_level"),
        "achieved_passing_at": data.get("achieved_passing_at"),
        "achieved_silver_at": data.get("achieved_silver_at"),
        "achieved_gold_at": data.get("achieved_gold_at"),
        "status_counts": counts,
        "status_fields": status_fields,
    }


class ProposalTooLong(ValueError):
    def __init__(self, artifact: dict[str, Any]) -> None:
        super().__init__(f"proposal URL exceeds {MAX_PROPOSAL_URL_LENGTH} characters")
        self.artifact = artifact


def proposal_url(project_id: int, section: str, answers: dict[str, Any]) -> str:
    """Build a validated, single-section proposal URL or fail without truncation."""
    if section not in {"passing", "silver", "gold"}:
        raise ValueError("proposal section must be passing, silver, or gold")
    schema = load_schema()
    errors = validate(answers, schema, section)
    if errors:
        raise ValueError("invalid proposal: " + "; ".join(errors))
    fields = schema["fields"]
    allowed: dict[str, Any] = {}
    for key, value in answers.items():
        if key.endswith("_status"):
            base = key[:-7]
            if section in fields[base]["levels"] and value not in {"?", "unknown", None}:
                allowed[key] = value
                justification = f"{base}_justification"
                if justification in answers:
                    allowed[justification] = answers[justification]
    query = urlencode(allowed)
    url = f"{BASE}/en/projects/{project_id}/{section}/edit?{query}"
    if len(url) > MAX_PROPOSAL_URL_LENGTH:
        raise ProposalTooLong({
            "project_id": project_id,
            "section": section,
            "answers": allowed,
            "reason": "URL exceeds conservative 8,000-character limit; split by section or field groups.",
        })
    return url


def preflight() -> int:
    """Check dependencies without assuming a ``python`` command exists."""
    python_version = tuple(sys.version_info[:2])
    required = ["git", "gh"]
    missing = [name for name in required if not shutil.which(name)]
    executors = [
        name for name in ("scorecard", "podman", "docker", "nerdctl") if shutil.which(name)
    ]
    result = {
        "python_executable": sys.executable,
        "python_version": ".".join(map(str, python_version)),
        "required": {name: shutil.which(name) for name in required},
        "scorecard_executors": executors,
        "missing": missing,
    }
    if python_version < MIN_PYTHON_VERSION:
        print(
            "ERROR: preflight requires Python "
            f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+; "
            "rerun with a supported Python 3 interpreter.",
            file=sys.stderr,
        )
        return 3
    if missing or not executors:
        unavailable = missing or ["scorecard, podman, docker, or nerdctl"]
        print(
            "ERROR: preflight missing required tool(s): " + ", ".join(unavailable) + ".",
            file=sys.stderr,
        )
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def write_json(path: Path, data: Any) -> None:
    """Write through the shared atomic output API (never direct Path writes)."""
    root = path.parent.resolve()
    atomic_write_text(
        root,
        path.name,
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight")

    discover = sub.add_parser("discover")
    discover.add_argument("--output", type=Path)
    discover.add_argument("--private-consent", choices=("bestpractices.dev",))

    fetch = sub.add_parser("fetch")
    fetch.add_argument("--project-id", type=int, required=True)
    fetch.add_argument("--output", type=Path, required=True)

    summarize = sub.add_parser("summarize")
    summarize.add_argument("--project", type=Path)
    summarize.add_argument("--scorecard", type=Path)
    summarize.add_argument("--output", type=Path, required=True)

    proposal = sub.add_parser("proposal-url")
    proposal.add_argument("--project-id", type=int, required=True)
    proposal.add_argument("--section", choices=("passing", "silver", "gold"), required=True)
    proposal.add_argument("--answers", type=Path, required=True)
    proposal.add_argument("--fallback-output", type=Path)

    args = parser.parse_args()

    try:
        if args.command == "preflight":
            return preflight()
        if args.command == "discover":
            data = discover_ids(args.private_consent)
            if args.output:
                write_json(args.output, data)
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0 if data["enrolment"] != "ambiguous" else 2
        if args.command == "fetch":
            data = fetch_project(args.project_id)
            write_json(args.output, data)
            print(json.dumps(project_summary(data), indent=2, sort_keys=True))
            return 0
        if args.command == "summarize":
            if not args.project or not args.project.is_file():
                raise ValueError("summarize requires a valid --project evidence file")
            result: dict[str, Any] = {
                "best_practices": project_summary(json.loads(args.project.read_text(encoding="utf-8"))),
                "evidence_state": {"project": "available"},
            }
            if args.scorecard:
                if not args.scorecard.is_file():
                    raise ValueError("requested Scorecard evidence is missing")
                result["scorecard"] = scorecard_summary(json.loads(args.scorecard.read_text(encoding="utf-8")))
                result["evidence_state"]["scorecard"] = "available"
            else:
                result["evidence_state"]["scorecard"] = "not_requested"
            write_json(args.output, result)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "proposal-url":
            answers = json.loads(args.answers.read_text(encoding="utf-8"))
            try:
                print(proposal_url(args.project_id, args.section, answers))
            except ProposalTooLong as exc:
                if not args.fallback_output:
                    raise ValueError(f"{exc}; provide --fallback-output for the local proposal artifact") from exc
                write_json(args.fallback_output, exc.artifact)
                print(json.dumps({"proposal_url": None, "fallback": str(args.fallback_output), "instructions": exc.artifact["reason"]}))
            return 0
    except PrivacyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError, HTTPError, URLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
