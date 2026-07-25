#!/usr/bin/env python3
"""Run OpenSSF Scorecard locally or with an available container runtime.

Authentication is read from process-local environment variables or ``gh auth
token`` and is passed to Scorecard through ``GITHUB_AUTH_TOKEN``. Token values
are never placed in command arguments or emitted in output.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

# Reviewed immutable OCI image. Update only after reviewing the upstream release.
SCORECARD_IMAGE = "ghcr.io/ossf/scorecard@sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795"
CONTAINER_RUNTIMES = ("docker", "podman", "nerdctl")


def token_from_gh_cli() -> str | None:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True,
            shell=False, check=False, timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip() if result.returncode == 0 else ""
    return token or None


def discover_token() -> tuple[str | None, str | None]:
    """Return a token and a non-secret source label."""
    for name in ("GITHUB_AUTH_TOKEN", "GITHUB_TOKEN"):
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    token = token_from_gh_cli()
    return (token, "gh auth token") if token else (None, None)


def _redact(message: str, token: str | None) -> str:
    return message.replace(token, "[REDACTED_TOKEN]") if token else message


def _scorecard_environment(token: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if token:
        # Scorecard documents GITHUB_AUTH_TOKEN. Keep it in the child process
        # environment only; never interpolate it into a command argument.
        env["GITHUB_AUTH_TOKEN"] = token
    return env


def _working_runtimes(preferred: str | None = None) -> list[str]:
    candidates = ([preferred] if preferred else []) + list(CONTAINER_RUNTIMES)
    working: list[str] = []
    for runtime in dict.fromkeys(name for name in candidates if name):
        executable = shutil.which(runtime)
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, "version"], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, shell=False, check=False, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            working.append(executable)
    return working


def _run_to_file(command: list[str], output_path: Path, env: dict[str, str], timeout: int) -> tuple[int, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            result = subprocess.run(
                command, stdout=output, stderr=subprocess.PIPE, text=True,
                env=env, shell=False, check=False, timeout=timeout,
            )
        if result.returncode == 0:
            # Validate before publishing a result that downstream code will read.
            with temporary.open(encoding="utf-8") as source:
                json.load(source)
            temporary.replace(output_path)
        else:
            temporary.unlink(missing_ok=True)
        return result.returncode, result.stderr.strip()
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
        temporary.unlink(missing_ok=True)
        return 1, str(exc)


def run_scorecard(
    repository: str,
    output_path: Path,
    token: str | None = None,
    timeout: int = 300,
    preferred_runtime: str | None = None,
    allow_container: bool = False,
) -> dict[str, Any]:
    """Run Scorecard and return non-secret execution metadata.

    A local ``scorecard`` binary takes precedence. If it is absent, each working
    Docker-compatible runtime is tried in order. The current image is pulled
    before execution; a cached image is still attempted if the pull fails.
    """
    if token is None:
        token, token_source = discover_token()
    else:
        token_source = "provided in process memory"
    env = _scorecard_environment(token)
    scorecard_args = ["--repo", f"github.com/{repository}", "--format", "json", "--show-details"]
    local = shutil.which("scorecard")
    if local:
        code, error = _run_to_file([local, *scorecard_args], output_path, env, timeout)
        return {
            "status": "success" if code == 0 else "failed",
            "executor": "local",
            "token_source": token_source,
            "output_path": str(output_path) if code == 0 else None,
            "error": _redact(error, token) or None,
        }

    if not allow_container:
        return {
            "status": "unavailable",
            "executor": None,
            "token_source": token_source,
            "output_path": None,
            "error": "local Scorecard is unavailable; pass explicit container approval to execute the reviewed container image",
        }

    errors: list[str] = []
    for runtime in _working_runtimes(preferred_runtime):
        runtime_name = Path(runtime).name
        try:
            pull = subprocess.run(
                [runtime, "pull", SCORECARD_IMAGE], stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, env=env, shell=False,
                check=False, timeout=timeout,
            )
            if pull.returncode != 0:
                errors.append(f"{runtime_name} pull: {_redact(pull.stderr.strip(), token)}")
        except (OSError, subprocess.SubprocessError) as exc:
            # A cached image may remain usable, so still attempt the run.
            errors.append(f"{runtime_name} pull: {_redact(str(exc), token)}")
        command = [runtime, "run", "--rm"]
        if token:
            # -e NAME forwards the value from subprocess env without exposing it
            # in argv, process listings, logs, or shell history.
            command.extend(["-e", "GITHUB_AUTH_TOKEN"])
        command.extend([SCORECARD_IMAGE, *scorecard_args])
        code, error = _run_to_file(command, output_path, env, timeout)
        if code == 0:
            return {
                "status": "success",
                "executor": runtime_name,
                "image": SCORECARD_IMAGE,
                "token_source": token_source,
                "output_path": str(output_path),
                "error": None,
            }
        errors.append(f"{runtime_name} run: {_redact(error, token)}")

    return {
        "status": "unavailable" if not errors else "failed",
        "executor": None,
        "token_source": token_source,
        "output_path": None,
        "error": "; ".join(errors) if errors else "scorecard is not installed and no working Docker-compatible runtime was found",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run OpenSSF Scorecard locally, falling back to a container")
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--output", required=True, type=Path, help="Scorecard JSON output path")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--container-runtime", help="Preferred Docker-compatible runtime executable")
    parser.add_argument("--allow-container", action="store_true", help="Explicitly allow execution of the reviewed Scorecard container image when no local binary is available")
    args = parser.parse_args(argv)
    result = run_scorecard(args.repo, args.output, timeout=args.timeout, preferred_runtime=args.container_runtime, allow_container=args.allow_container)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
