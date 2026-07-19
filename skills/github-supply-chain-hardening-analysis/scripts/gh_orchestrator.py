#!/usr/bin/env python3
"""Read-only GitHub organization or personal repository supply-chain analyzer.

Discovers repositories visible to a token, clones active repositories into isolated
temporary workspaces, runs deterministic local heuristics, and writes one
OpenSpec-style remediation proposal JSON file per repository.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Literal

from scorecard_runner import run_scorecard

try:
    from pydantic import BaseModel, ValidationError
    from github import Auth, Github
    from github.GithubException import BadCredentialsException, GithubException, RateLimitExceededException, UnknownObjectException
except Exception as exc:  # pragma: no cover - import-time operator guidance
    print(
        "ERROR: missing dependency. Install with: pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

ANALYSIS_VERSION = "2026.06.19"
SKIP_DIRS = {
    ".git",
    "node_modules",
    "bin",
    "obj",
    "target",
    ".venv",
    "venv",
    "vendor",
    "dist",
    "build",
    ".next",
    ".terraform",
}
WORKFLOW_GLOBS = [".github/workflows/*.yml", ".github/workflows/*.yaml"]
SECRET_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
]
CANDIDATE_PATTERNS = [
    *WORKFLOW_GLOBS,
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    ".github/CODEOWNERS",
    "CODEOWNERS",
    "SECURITY.md",
    ".github/SECURITY.md",
    "CONTRIBUTING.md",
    "README.md",
    "docs/threat-model.md",
    "docs/security.md",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile.lock",
    "poetry.lock",
    "*.csproj",
    "packages.lock.json",
    "Directory.Packages.props",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Dockerfile",
    "docker-compose.yml",
    "compose.yml",
    "*.tf",
    "Chart.yaml",
    "values.yaml",
    "templates/*.yaml",
    "templates/*.yml",
    *SECRET_FILE_PATTERNS,
]
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
USES_RE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
SHELL_CONTEXT_RE = re.compile(r"run:\s*(?:\|\s*)?[^\n]*(\$\{\{\s*github\.(event|head_ref|ref|actor|repository|sha)[^}]*\}\})", re.IGNORECASE)
TOKEN_NAME_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|client[_-]?secret|private[_-]?key)\s*[:=]")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
CLOUD_SECRET_RE = re.compile(r"(?i)(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AZURE_CLIENT_SECRET|GOOGLE_APPLICATION_CREDENTIALS|GCP_SERVICE_ACCOUNT|CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE)")


class ProposalChange(BaseModel):
    file_path: str
    action: str
    original_snippet: str
    proposed_snippet: str
    rationale: str


class OpenSpecProposal(BaseModel):
    repository_name: str
    repository_full_name: str
    generated_at_utc: str
    analysis_version: str
    target_goal: str
    estimated_risk: Literal["low", "medium", "high", "critical"]
    risk_drivers: list[str]
    control_areas: list[str]
    manual_review_required: bool
    scorecard_evidence: dict[str, Any]
    changes: list[ProposalChange]


@dataclass(frozen=True)
class RepoMetadata:
    name: str
    full_name: str
    clone_url: str
    default_branch: str | None
    private: bool
    archived: bool
    pushed_at: str | None
    updated_at: str | None
    language: str | None
    fork: bool


@dataclass
class Finding:
    control_area: str
    risk: Literal["low", "medium", "high", "critical"]
    file_path: str
    action: str
    title: str
    original_snippet: str
    proposed_snippet: str
    rationale: str


@dataclass
class AnalysisResult:
    findings: list[Finding] = field(default_factory=list)
    files_seen: set[str] = field(default_factory=set)
    ecosystems: set[str] = field(default_factory=set)
    workflow_files: list[str] = field(default_factory=list)


@dataclass
class RepoProcessResult:
    repository: str
    status: Literal["success", "failed", "timeout", "skipped"]
    proposal_path: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    scorecard_status: str | None = None
    scorecard_executor: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Read-only GitHub org/personal repository supply-chain analyzer")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--org", help="GitHub organization name")
    target.add_argument("--user", help="GitHub user account whose owned personal repositories should be analyzed")
    parser.add_argument("--token-source", choices=["auto", "env", "gh"], default="auto", help="Token source: auto checks GITHUB_TOKEN then gh auth token")
    parser.add_argument("--token", help="Optional GitHub token for local testing only; prefer --token-source or GITHUB_TOKEN")
    parser.add_argument("--output-dir", default="./proposals", help="Directory for proposal JSON files")
    parser.add_argument("--max-concurrency", type=int, default=5, help="Maximum repositories processed concurrently")
    parser.add_argument("--repo-timeout-seconds", type=int, default=600, help="Per-repository timeout")
    parser.add_argument("--clone-depth", type=int, default=1, help="Git clone depth")
    parser.add_argument("--dry-run", action="store_true", help="Discover only; skip cloning and proposal writing")
    parser.add_argument("--max-repositories", type=int, help="Limit active repositories processed after discovery; useful for confidence tests")
    parser.add_argument("--max-file-bytes", type=int, default=1_048_576, help="Maximum file size to read")
    parser.add_argument("--scorecard-timeout-seconds", type=int, default=300, help="Scorecard execution/pull timeout")
    parser.add_argument("--container-runtime", help="Preferred Docker-compatible runtime when local Scorecard is unavailable")
    return parser.parse_args(argv)


def _token_from_gh_cli() -> str | None:
    """Return the active GitHub CLI token without printing it."""
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
        return None
    if completed.returncode != 0:
        return None
    token = completed.stdout.strip()
    return token or None


def get_token(args: argparse.Namespace) -> str:
    """Return token from the selected source without printing it."""
    if args.token:
        return args.token
    env_token = os.environ.get("GITHUB_TOKEN")
    if args.token_source == "env":
        token = env_token
    elif args.token_source == "gh":
        token = _token_from_gh_cli()
    else:
        token = env_token or _token_from_gh_cli()
    if not token:
        raise RuntimeError("missing token: set GITHUB_TOKEN, run gh auth login, or pass --token for local testing")
    return token


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "astimezone"):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def discover_repositories(target_type: Literal["organization", "user"], target_name: str, token: str) -> tuple[list[RepoMetadata], int, int]:
    """Authenticate, resolve an organization or user, and list visible repositories."""
    print(f"Discovery started for {target_type}: {target_name}", flush=True)
    gh = Github(auth=Auth.Token(token), per_page=100)
    try:
        if target_type == "organization":
            org = gh.get_organization(target_name)
            repos = list(org.get_repos(type="all"))
        else:
            authenticated_user = gh.get_user()
            authenticated_login = getattr(authenticated_user, "login", None)
            if authenticated_login and authenticated_login.lower() == target_name.lower():
                repos = list(authenticated_user.get_repos(affiliation="owner"))
            else:
                user = gh.get_user(target_name)
                repos = list(user.get_repos(type="owner"))
    except BadCredentialsException as exc:
        raise RuntimeError("authentication failure: GitHub rejected the provided token") from exc
    except UnknownObjectException as exc:
        raise RuntimeError(f"{target_type} not found or not visible to token: {target_name}") from exc
    except RateLimitExceededException as exc:
        raise RuntimeError("GitHub API rate limiting encountered during discovery") from exc
    except GithubException as exc:
        raise RuntimeError(f"GitHub API error during discovery: {exc.data if hasattr(exc, 'data') else exc}") from exc

    archived_count = sum(1 for repo in repos if bool(repo.archived))
    fork_count = sum(1 for repo in repos if bool(getattr(repo, "fork", False)) and not bool(repo.archived))
    active: list[RepoMetadata] = []
    for repo in repos:
        metadata = RepoMetadata(
            name=repo.name,
            full_name=repo.full_name,
            clone_url=repo.clone_url,
            default_branch=getattr(repo, "default_branch", None),
            private=bool(repo.private),
            archived=bool(repo.archived),
            pushed_at=_iso_or_none(getattr(repo, "pushed_at", None)),
            updated_at=_iso_or_none(getattr(repo, "updated_at", None)),
            language=getattr(repo, "language", None),
            fork=bool(getattr(repo, "fork", False)),
        )
        if not metadata.archived and not metadata.fork:
            active.append(metadata)
    print(f"Repositories discovered: {len(repos)}", flush=True)
    print(f"Archived repositories skipped: {archived_count}", flush=True)
    print(f"Forks skipped: {fork_count}", flush=True)
    return active, archived_count, fork_count


def make_authenticated_clone_url(clone_url: str, token: str) -> str:
    """Construct an authenticated HTTPS clone URL for git only.

    The returned value must never be logged or persisted.
    """
    if not clone_url.startswith("https://"):
        raise ValueError("only HTTPS clone URLs are supported")
    return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)


def _sanitize_message(message: str, token: str) -> str:
    safe = message.replace(token, "[REDACTED_TOKEN]") if token else message
    safe = re.sub(r"https://x-access-token:[^@\s]+@", "https://x-access-token:[REDACTED]@", safe)
    return safe


def clone_repository(repo: RepoMetadata, token: str, destination: Path, clone_depth: int) -> None:
    """Clone one repository into destination using argument-list subprocess calls."""
    clone_url = make_authenticated_clone_url(repo.clone_url, token)
    cmd = [
        "git",
        "clone",
        "--depth",
        str(clone_depth),
        "--no-tags",
        "--single-branch",
    ]
    if repo.default_branch:
        cmd.extend(["--branch", repo.default_branch])
    cmd.extend([clone_url, str(destination)])
    completed = subprocess.run(cmd, capture_output=True, text=True, shell=False, check=False)
    if completed.returncode != 0:
        stderr = _sanitize_message(completed.stderr.strip(), token)
        stdout = _sanitize_message(completed.stdout.strip(), token)
        detail = stderr or stdout or f"git clone exited {completed.returncode}"
        raise RuntimeError(f"clone failed for {repo.full_name}: {detail}")


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _looks_like_kubernetes_yaml(text: str) -> bool:
    return bool(re.search(r"(?m)^kind:\s*(Deployment|StatefulSet|DaemonSet|Pod|Service|Ingress|Job|CronJob|ConfigMap|Secret)\b", text))


def iter_candidate_files(root: Path, max_file_bytes: int) -> list[Path]:
    """Return candidate files while skipping generated/vendor directories and huge files."""
    candidates: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        current = Path(current_root)
        for filename in filenames:
            path = current / filename
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            rel = _relative_posix(root, path)
            lower = rel.lower()
            if _matches_any(rel, CANDIDATE_PATTERNS) or lower.endswith((".yaml", ".yml")):
                candidates.append(path)
    return sorted(candidates)


def read_text_limited(path: Path, max_file_bytes: int) -> str | None:
    """Read a bounded text file; return None for large/binary/unreadable files."""
    try:
        if path.stat().st_size > max_file_bytes:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _add(result: AnalysisResult, finding: Finding) -> None:
    result.findings.append(finding)


def _detect_ecosystems(rel: str, result: AnalysisResult) -> None:
    name = Path(rel).name
    if name in {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        result.ecosystems.add("npm/javascript")
    if name in {"requirements.txt", "pyproject.toml", "Pipfile.lock", "poetry.lock"}:
        result.ecosystems.add("python")
    if name.endswith(".csproj") or name in {"packages.lock.json", "Directory.Packages.props"}:
        result.ecosystems.add("nuget")
    if name in {"pom.xml", "build.gradle", "build.gradle.kts", "gradle.lockfile"}:
        result.ecosystems.add("maven/gradle")
    if name in {"go.mod", "go.sum"}:
        result.ecosystems.add("go")
    if name in {"Cargo.toml", "Cargo.lock"}:
        result.ecosystems.add("rust")
    if name in {"Dockerfile", "docker-compose.yml", "compose.yml"}:
        result.ecosystems.add("docker")
    if rel.startswith(".github/workflows/"):
        result.ecosystems.add("github-actions")
    if rel.endswith(".tf"):
        result.ecosystems.add("terraform")


def _analyze_workflow(rel: str, text: str, result: AnalysisResult) -> None:
    result.workflow_files.append(rel)
    if not re.search(r"(?m)^permissions\s*:", text):
        _add(result, Finding(
            "github_actions", "medium", rel, "modify", "Missing explicit workflow permissions",
            "No top-level permissions block detected.",
            "permissions:\n  contents: read\n",
            "Heuristic finding: set default GITHUB_TOKEN permissions to least privilege and elevate per job only when required.",
        ))
    elif re.search(r"(?m)^permissions\s*:\s*(write-all|read-all)", text) or re.search(r"(?m)^\s*contents:\s*write\b", text):
        _add(result, Finding(
            "github_actions", "medium", rel, "review", "Broad workflow permissions",
            "Workflow appears to request broad or write permissions.",
            "Use top-level `permissions: { contents: read }` and grant narrow job-level writes only where justified.",
            "Heuristic finding: broad GITHUB_TOKEN permissions increase blast radius if workflow steps or dependencies are compromised.",
        ))
    for match in USES_RE.finditer(text):
        uses = match.group(1).strip().strip('"\'')
        if "@" not in uses or uses.startswith("./"):
            continue
        ref = uses.rsplit("@", 1)[1]
        if ref in {"main", "master", "develop", "dev", "HEAD"} or not FULL_SHA_RE.match(ref):
            _add(result, Finding(
                "github_actions", "high" if ref in {"main", "master"} else "medium", rel, "modify", "Mutable action reference",
                f"uses: {uses}",
                "Pin third-party actions to reviewed full-length commit SHAs and track updates with automation.",
                "Heuristic finding: mutable action references can change without review and are a common CI supply-chain risk.",
            ))
    if "pull_request_target" in text:
        _add(result, Finding(
            "github_actions", "high", rel, "review", "Potentially dangerous pull_request_target usage",
            "Workflow uses pull_request_target.",
            "Review whether untrusted pull request code can influence checked-out code, scripts, labels, comments, artifacts, or secrets.",
            "Heuristic finding: pull_request_target runs with base-repository privileges and can expose write tokens or secrets if misused.",
        ))
    if SHELL_CONTEXT_RE.search(text):
        _add(result, Finding(
            "github_actions", "medium", rel, "review", "Untrusted GitHub context in shell command",
            "A run step appears to interpolate github.* context directly.",
            "Move untrusted context values into environment variables, quote defensively, and validate before shell use.",
            "Heuristic finding: direct interpolation of attacker-controlled context can cause command injection.",
        ))
    if CLOUD_SECRET_RE.search(text) or re.search(r"(?i)secrets\.(AWS|AZURE|GCP|GOOGLE|CLOUD)", text):
        _add(result, Finding(
            "secrets", "high", rel, "modify", "Static cloud credential reference",
            "Workflow references cloud credential secrets or files.",
            "Migrate cloud authentication to GitHub OIDC federation with explicit `id-token: write` only in the deployment job.",
            "Heuristic finding: long-lived cloud secrets in CI increase credential theft and rotation risk.",
        ))
    if re.search(r"(?i)(release|publish|deploy|build|package|artifact)", rel + "\n" + text) and "attest" not in text.lower():
        _add(result, Finding(
            "release_provenance", "medium", rel, "modify", "Missing artifact attestation recommendation",
            "Build/release workflow detected without artifact attestation references.",
            "Add GitHub artifact attestations or SLSA provenance generation for release artifacts and packages.",
            "Heuristic finding: provenance improves downstream verification of build origin and integrity.",
        ))
    if "self-hosted" in text:
        _add(result, Finding(
            "github_actions", "high", rel, "review", "Self-hosted runner isolation review",
            "Workflow uses self-hosted runners.",
            "Require ephemeral isolated runners, restricted repository access, hardened network egress, and no untrusted pull request execution.",
            "Heuristic finding: persistent self-hosted runners can retain attacker state or secrets across jobs.",
        ))
    if re.search(r"(?i)(npm publish|twine upload|dotnet nuget push|mvn deploy|gradle publish|cargo publish|docker push)", text):
        _add(result, Finding(
            "release_provenance", "high", rel, "review", "Package publishing hardening",
            "Package publishing command detected.",
            "Use trusted publishing/OIDC where supported, environment approvals, least-privilege tokens, and artifact provenance.",
            "Heuristic finding: package publishing workflows are high-value supply-chain targets and require stronger controls.",
        ))


def _analyze_dockerfile(rel: str, text: str, result: AnalysisResult) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("FROM "):
            continue
        image = stripped.split()[1]
        if ":latest" in image or (":" not in image and "@sha256:" not in image):
            _add(result, Finding(
                "dependencies", "medium", rel, "modify", "Unpinned Docker base image",
                stripped,
                "Pin base images by immutable digest, for example `FROM image:tag@sha256:<digest>`.",
                "Heuristic finding: mutable container base tags can introduce unreviewed dependencies into builds.",
            ))


def _analyze_secret_indicators(rel: str, text: str, result: AnalysisResult) -> None:
    name = Path(rel).name
    if _matches_any(name, SECRET_FILE_PATTERNS) or _matches_any(rel, SECRET_FILE_PATTERNS):
        _add(result, Finding(
            "secrets", "critical", rel, "review", "Sensitive filename detected",
            f"Sensitive-looking file path: {rel}",
            "Remove real secrets from source control, rotate affected credentials, and replace with secret manager/OIDC references.",
            "Heuristic finding: the file name suggests possible credentials. Values are intentionally not copied into this proposal.",
        ))
    if PRIVATE_KEY_RE.search(text):
        _add(result, Finding(
            "secrets", "critical", rel, "review", "Private key material pattern detected",
            "Private key header pattern detected; value redacted.",
            "Treat as credential exposure until proven otherwise: remove, rotate, and enable secret scanning with push protection.",
            "Heuristic finding: private-key-like material was detected without including the secret value.",
        ))
    if TOKEN_NAME_RE.search(text) or CLOUD_SECRET_RE.search(text):
        _add(result, Finding(
            "secrets", "high", rel, "review", "Credential variable indicator detected",
            "Credential-like variable name detected; value redacted.",
            "Verify no hardcoded credentials are present. Use secret scanning, push protection, and short-lived federated credentials.",
            "Heuristic finding: credential-like names can be benign configuration, but require manual review.",
        ))


def analyze_repository(repo_path: Path, max_file_bytes: int) -> AnalysisResult:
    """Run deterministic local static heuristics against one cloned repository."""
    result = AnalysisResult()
    file_texts: dict[str, str] = {}
    for path in iter_candidate_files(repo_path, max_file_bytes):
        rel = _relative_posix(repo_path, path)
        text = read_text_limited(path, max_file_bytes)
        if text is None:
            continue
        if rel.lower().endswith((".yaml", ".yml")) and not (_matches_any(rel, CANDIDATE_PATTERNS) or _looks_like_kubernetes_yaml(text)):
            continue
        result.files_seen.add(rel)
        file_texts[rel] = text
        _detect_ecosystems(rel, result)
        if _matches_any(rel, WORKFLOW_GLOBS):
            _analyze_workflow(rel, text, result)
        if Path(rel).name == "Dockerfile":
            _analyze_dockerfile(rel, text, result)
        _analyze_secret_indicators(rel, text, result)
        if _looks_like_kubernetes_yaml(text):
            result.ecosystems.add("kubernetes")

    if not ({".github/dependabot.yml", ".github/dependabot.yaml"} & result.files_seen):
        _add(result, Finding(
            "dependencies", "medium", ".github/dependabot.yml", "create", "Missing Dependabot configuration",
            "No .github/dependabot.yml or .github/dependabot.yaml detected.",
            "Create Dependabot security and version update configuration for detected ecosystems.",
            "Heuristic finding: Dependabot configuration helps keep dependencies current and security updates visible.",
        ))
    if result.workflow_files and not any("dependency-review" in file_texts.get(f, "").lower() for f in result.workflow_files):
        _add(result, Finding(
            "dependencies", "medium", ".github/workflows/dependency-review.yml", "create", "Missing dependency review workflow",
            "No dependency review action usage detected.",
            "Add a pull_request workflow using actions/dependency-review-action pinned to a full-length commit SHA.",
            "Heuristic finding: dependency review before merge can block vulnerable or policy-violating dependency changes.",
        ))
    if result.workflow_files and not any("scorecard" in file_texts.get(f, "").lower() for f in result.workflow_files):
        _add(result, Finding(
            "dependencies", "low", ".github/workflows/scorecard.yml", "create", "Missing OpenSSF Scorecard workflow",
            "No OpenSSF Scorecard workflow detected.",
            "Add a scheduled OpenSSF Scorecard workflow with least-privilege permissions and reviewed token scope.",
            "Heuristic finding: Scorecard provides broad supply-chain hygiene signals for maintainers.",
        ))
    if "package.json" in result.files_seen and not ({"package-lock.json", "pnpm-lock.yaml", "yarn.lock"} & result.files_seen):
        _add(result, Finding(
            "dependencies", "high", "package-lock.json", "create", "Missing JavaScript lockfile",
            "package.json detected without npm, pnpm, or yarn lockfile.",
            "Commit an ecosystem-appropriate lockfile and enforce reproducible installs in CI.",
            "Heuristic finding: missing lockfiles reduce reproducibility and increase dependency confusion/typosquatting risk.",
        ))
    if "pyproject.toml" in result.files_seen and not ({"poetry.lock", "Pipfile.lock"} & result.files_seen):
        _add(result, Finding(
            "dependencies", "medium", "poetry.lock", "create", "Missing Python lockfile",
            "pyproject.toml detected without poetry.lock or Pipfile.lock.",
            "Use a lockfile or another reproducible dependency pinning strategy appropriate for the project type.",
            "Heuristic finding: Python library projects vary, so this requires manual review.",
        ))
    if "Cargo.toml" in result.files_seen and "Cargo.lock" not in result.files_seen:
        _add(result, Finding(
            "dependencies", "medium", "Cargo.lock", "create", "Missing Cargo.lock",
            "Cargo.toml detected without Cargo.lock.",
            "Commit Cargo.lock for applications/binaries, or document why a library intentionally omits it.",
            "Heuristic finding: Cargo lockfile expectations depend on crate type and require manual review.",
        ))
    if not ({"CODEOWNERS", ".github/CODEOWNERS"} & result.files_seen):
        _add(result, Finding(
            "governance", "medium", "CODEOWNERS", "create", "Missing CODEOWNERS",
            "No CODEOWNERS file detected.",
            "Create CODEOWNERS aligned to responsible teams and require owner review for sensitive paths.",
            "Heuristic finding: CODEOWNERS improves review routing and accountability for sensitive changes.",
        ))
    if not ({"SECURITY.md", ".github/SECURITY.md"} & result.files_seen):
        _add(result, Finding(
            "governance", "medium", "SECURITY.md", "create", "Missing SECURITY.md",
            "No SECURITY.md file detected.",
            "Add a SECURITY.md with supported versions, vulnerability reporting path, and response expectations.",
            "Heuristic finding: a clear disclosure path reduces vulnerability handling ambiguity.",
        ))
    if not ({"docs/threat-model.md", "docs/security.md"} & result.files_seen):
        _add(result, Finding(
            "sdlc_documentation", "low", "docs/threat-model.md", "create", "Missing threat model or security architecture notes",
            "No docs/threat-model.md or docs/security.md detected.",
            "Document assets, trust boundaries, abuse cases, dependencies, and security-sensitive decisions.",
            "Heuristic finding: security documentation supports auditability and secure design review.",
        ))
    if not any("codeql" in file_texts.get(f, "").lower() or "sarif" in file_texts.get(f, "").lower() for f in result.workflow_files):
        _add(result, Finding(
            "code_security", "medium", ".github/workflows/codeql.yml", "create", "Missing code scanning workflow",
            "No CodeQL or SARIF upload workflow detected.",
            "Enable CodeQL or an equivalent SAST scanner with SARIF upload and required triage expectations.",
            "Heuristic finding: code scanning presence could also be configured outside workflow files and requires manual review.",
        ))
    _add(result, Finding(
        "governance", "medium", "GITHUB_REPOSITORY_SETTINGS", "configure", "Branch protection and ruleset hardening review",
        "Repository settings were not mutated by this read-only analysis.",
        "Configure repository rulesets or branch protection requiring pull requests, CODEOWNERS review, status checks, code scanning, dependency review, signed commits/tags where appropriate, and force-push/deletion restrictions.",
        "Heuristic recommendation: repository settings require API/settings verification and manual rollout planning.",
    ))
    _add(result, Finding(
        "secrets", "high", "GITHUB_REPOSITORY_SETTINGS", "configure", "Secret scanning and push protection review",
        "Repository settings were not mutated by this read-only analysis.",
        "Enable secret scanning, push protection, and custom patterns for organization-specific credentials where available.",
        "Heuristic recommendation: secret scanning and push protection reduce accidental credential exposure.",
    ))
    _add(result, Finding(
        "ai_agentic_workflows", "medium", "GITHUB_ORGANIZATION_RULESET", "configure", "AI and agentic workflow guardrails",
        "Organization rulesets were not mutated by this read-only analysis.",
        "Require human review for AI-generated code, scope agent credentials narrowly, prevent unreviewed agent repository mutation, and require dependency/security review for generated changes.",
        "Heuristic recommendation: agentic workflows create new supply-chain and prompt-injection risks that need explicit governance.",
    ))
    return result


def _risk_rank(risk: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(risk, 1)


def summarize_scorecard(execution: dict[str, Any]) -> dict[str, Any]:
    """Add a bounded check summary to Scorecard execution metadata."""
    evidence = dict(execution)
    output_path = execution.get("output_path")
    if execution.get("status") != "success" or not output_path:
        evidence["overall_score"] = None
        evidence["checks"] = []
        return evidence
    try:
        payload = json.loads(Path(output_path).read_text(encoding="utf-8"))
        checks = []
        for check in payload.get("checks", []):
            score = check.get("score")
            # This is a prioritization band derived from the numeric check score,
            # not a risk label emitted by Scorecard itself.
            risk = "unknown"
            if isinstance(score, (int, float)):
                risk = "critical" if score <= 2 else "high" if score <= 5 else "medium" if score <= 7 else "low"
            checks.append({
                "name": check.get("name"),
                "score": score,
                "derived_risk_rating": risk,
                "reason": check.get("reason"),
            })
        evidence["overall_score"] = payload.get("score")
        evidence["checks"] = sorted(checks, key=lambda item: (item["score"] is None, item["score"] if item["score"] is not None else 99))
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        evidence["status"] = "failed"
        evidence["error"] = f"could not summarize Scorecard JSON: {exc}"
        evidence["overall_score"] = None
        evidence["checks"] = []
    return evidence


def build_proposal(repo: RepoMetadata, analysis: AnalysisResult, scorecard_evidence: dict[str, Any]) -> OpenSpecProposal:
    """Build and validate an OpenSpec-style proposal from findings."""
    findings = analysis.findings
    if not findings:
        findings = [Finding(
            "governance", "low", "GITHUB_REPOSITORY_SETTINGS", "review", "Manual repository governance review",
            "No high-confidence file-based findings were generated.",
            "Review repository rulesets, branch protection, secret scanning, dependency security, and release controls.",
            "Heuristic fallback: settings and organization controls may not be visible from a local clone.",
        )]
    estimated = max((f.risk for f in findings), key=_risk_rank)
    changes = [ProposalChange(
        file_path=f.file_path,
        action=f.action,
        original_snippet=f.original_snippet,
        proposed_snippet=f.proposed_snippet,
        rationale=f"{f.title}: {f.rationale}",
    ) for f in findings]
    risk_drivers = sorted({f.title for f in findings})[:50]
    control_areas = sorted({f.control_area for f in findings})
    return OpenSpecProposal(
        repository_name=repo.name,
        repository_full_name=repo.full_name,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        analysis_version=ANALYSIS_VERSION,
        target_goal="Harden repository supply-chain, secure-SDLC, release integrity, and agentic workflow controls without mutating the repository.",
        estimated_risk=estimated,
        risk_drivers=risk_drivers,
        control_areas=control_areas,
        manual_review_required=True,
        scorecard_evidence=scorecard_evidence,
        changes=changes,
    )


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # pydantic v2
    return model.dict()  # pydantic v1


def _safe_repo_name(full_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", full_name.strip())
    safe = safe.strip("._")
    return safe or "repository"


def write_proposal(proposal: OpenSpecProposal, output_dir: Path) -> Path:
    """Validate and write a pretty JSON proposal to the output directory."""
    if not proposal.changes:
        raise ValueError("proposal validation failed: changes must be non-empty")
    # Re-validate to catch accidental construction changes across pydantic versions.
    data = _model_to_dict(proposal)
    validated = OpenSpecProposal(**data)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{_safe_repo_name(validated.repository_full_name)}.json"
    path.write_text(json.dumps(_model_to_dict(validated), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


async def _process_repository_impl(
    repo: RepoMetadata,
    token: str,
    output_dir: Path,
    clone_depth: int,
    max_file_bytes: int,
    scorecard_timeout_seconds: int,
    container_runtime: str | None,
) -> RepoProcessResult:
    started = time.monotonic()
    temp_dir = Path(tempfile.mkdtemp(prefix="gh-org-supply-chain-"))
    clone_dir = temp_dir / "repo"
    try:
        await asyncio.to_thread(clone_repository, repo, token, clone_dir, clone_depth)
        analysis = await asyncio.to_thread(analyze_repository, clone_dir, max_file_bytes)
        scorecard_path = output_dir / "scorecards" / f"{_safe_repo_name(repo.full_name)}.json"
        scorecard_execution = await asyncio.to_thread(
            run_scorecard,
            repo.full_name,
            scorecard_path,
            token,
            scorecard_timeout_seconds,
            container_runtime,
        )
        scorecard_evidence = summarize_scorecard(scorecard_execution)
        if scorecard_evidence["status"] != "success":
            _add(analysis, Finding(
                "dependencies", "medium", "OPENSSF_SCORECARD", "review", "OpenSSF Scorecard evidence unavailable",
                scorecard_evidence.get("error") or "Scorecard execution did not produce JSON evidence.",
                "Install Scorecard or start Docker, Podman, or nerdctl, then rerun the analysis.",
                "Scorecard is a primary evidence source; this proposal contains heuristic findings only when its execution fails.",
            ))
        proposal = build_proposal(repo, analysis, scorecard_evidence)
        proposal_path = await asyncio.to_thread(write_proposal, proposal, output_dir)
        return RepoProcessResult(
            repo.full_name,
            "success",
            str(proposal_path),
            duration_seconds=time.monotonic() - started,
            scorecard_status=scorecard_evidence["status"],
            scorecard_executor=scorecard_evidence.get("executor"),
        )
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def process_repository(
    repo: RepoMetadata,
    token: str,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    repo_timeout_seconds: int,
    clone_depth: int,
    max_file_bytes: int,
    scorecard_timeout_seconds: int,
    container_runtime: str | None,
    dry_run: bool,
) -> RepoProcessResult:
    """Process one repository under semaphore and per-repository timeout."""
    async with semaphore:
        print(f"Worker start: {repo.full_name}", flush=True)
        started = time.monotonic()
        if dry_run:
            print(f"Worker skip: {repo.full_name} (dry-run)", flush=True)
            return RepoProcessResult(repo.full_name, "skipped", error="dry-run", duration_seconds=0.0)
        try:
            result = await asyncio.wait_for(
                _process_repository_impl(
                    repo, token, output_dir, clone_depth, max_file_bytes,
                    scorecard_timeout_seconds, container_runtime,
                ),
                timeout=repo_timeout_seconds,
            )
            print(f"Worker success: {repo.full_name}", flush=True)
            return result
        except asyncio.TimeoutError:
            print(f"Worker timeout: {repo.full_name}", flush=True)
            return RepoProcessResult(repo.full_name, "timeout", error=f"timed out after {repo_timeout_seconds}s", duration_seconds=time.monotonic() - started)
        except (ValidationError, ValueError) as exc:
            print(f"Worker failure: {repo.full_name} (proposal validation)", flush=True)
            return RepoProcessResult(repo.full_name, "failed", error=f"proposal validation failure: {exc}", duration_seconds=time.monotonic() - started)
        except Exception as exc:  # continue with other repositories
            safe_error = _sanitize_message(str(exc), token)
            print(f"Worker failure: {repo.full_name}", flush=True)
            return RepoProcessResult(repo.full_name, "failed", error=safe_error, duration_seconds=time.monotonic() - started)


def _result_to_dict(result: RepoProcessResult) -> dict[str, Any]:
    return {
        "repository": result.repository,
        "status": result.status,
        "proposal_path": result.proposal_path,
        "error": result.error,
        "duration_seconds": round(result.duration_seconds, 3),
        "scorecard_status": result.scorecard_status,
        "scorecard_executor": result.scorecard_executor,
    }


async def main_async(args: argparse.Namespace) -> int:
    """Main asynchronous orchestration entrypoint."""
    token = get_token(args)
    if args.max_concurrency < 1:
        raise RuntimeError("--max-concurrency must be at least 1")
    if args.repo_timeout_seconds < 1:
        raise RuntimeError("--repo-timeout-seconds must be at least 1")
    if args.clone_depth < 1:
        raise RuntimeError("--clone-depth must be at least 1")
    if args.scorecard_timeout_seconds < 1:
        raise RuntimeError("--scorecard-timeout-seconds must be at least 1")
    if args.max_repositories is not None and args.max_repositories < 1:
        raise RuntimeError("--max-repositories must be at least 1 when provided")
    output_dir = Path(args.output_dir).expanduser().resolve()
    try:
        if not args.dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"output directory creation failure: {output_dir}: {exc}") from exc

    target_type: Literal["organization", "user"] = "organization" if args.org else "user"
    target_name = args.org or args.user
    if not target_name:
        raise RuntimeError("missing target: pass --org or --user")
    active_repos, archived_count, fork_count = await asyncio.to_thread(discover_repositories, target_type, target_name, token)
    active_repositories_discovered = len(active_repos)
    if args.max_repositories is not None:
        active_repos = active_repos[:args.max_repositories]
        print(f"Active repository processing limited to: {len(active_repos)}", flush=True)
    if args.dry_run:
        print("Dry-run repositories selected:", flush=True)
        for repo in active_repos:
            print(f"- {repo.full_name}", flush=True)
    semaphore = asyncio.Semaphore(args.max_concurrency)
    tasks = [
        asyncio.create_task(process_repository(
            repo=repo,
            token=token,
            output_dir=output_dir,
            semaphore=semaphore,
            repo_timeout_seconds=args.repo_timeout_seconds,
            clone_depth=args.clone_depth,
            max_file_bytes=args.max_file_bytes,
            scorecard_timeout_seconds=args.scorecard_timeout_seconds,
            container_runtime=args.container_runtime,
            dry_run=args.dry_run,
        ))
        for repo in active_repos
    ]
    results = await asyncio.gather(*tasks) if tasks else []
    counts = {"success": 0, "failed": 0, "timeout": 0, "skipped": 0}
    for result in results:
        counts[result.status] += 1
    summary = {
        "target_type": target_type,
        "target": target_name,
        "organization": args.org,
        "user": args.user,
        "repositories_discovered": active_repositories_discovered + archived_count + fork_count,
        "archived_repositories_skipped": archived_count,
        "forks_skipped": fork_count,
        "active_repositories_discovered": active_repositories_discovered,
        "active_repositories_limited_to": len(active_repos) if args.max_repositories is not None else None,
        "active_repositories_analyzed": counts["success"],
        "proposals_generated": counts["success"],
        "repositories_failed": counts["failed"],
        "repositories_timed_out": counts["timeout"],
        "repositories_skipped": counts["skipped"],
        "scorecard_succeeded": sum(1 for result in results if result.scorecard_status == "success"),
        "scorecard_failed": sum(1 for result in results if result.scorecard_status == "failed"),
        "scorecard_unavailable": sum(1 for result in results if result.scorecard_status == "unavailable"),
        "output_dir": str(output_dir),
        "dry_run": bool(args.dry_run),
        "no_repository_changes_made": True,
        "results": [_result_to_dict(r) for r in results],
    }
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Synchronous console entrypoint. Non-zero only for global setup errors."""
    args = parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
