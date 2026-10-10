#!/usr/bin/env python3
"""Run approved immutable Scorecard with one deadline and bounded output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

from bounded_process import run, run_container
from safe_output import atomic_write_text

SCORECARD_IMAGE = "ghcr.io/ossf/scorecard@sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795"
CONTAINER_RUNTIMES = ("docker", "podman", "nerdctl")


def token_from_gh_cli() -> str | None:
    try:
        result = run(["gh", "auth", "token"], timeout=15, stdout_limit=4096)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def discover_token() -> tuple[str | None, str | None]:
    for name in ("GITHUB_AUTH_TOKEN", "GITHUB_TOKEN"):
        if token := os.environ.get(name, "").strip():
            return token, name
    token = token_from_gh_cli()
    return (token, "gh auth token") if token else (None, None)


def _redact(message: str, token: str | None) -> str:
    return message.replace(token, "[REDACTED_TOKEN]") if token else message


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise subprocess.TimeoutExpired("Scorecard", 0)
    return value


def working_runtime(preferred: str | None, deadline: float) -> str | None:
    for name in dict.fromkeys(([preferred] if preferred else []) + list(CONTAINER_RUNTIMES)):
        runtime = shutil.which(name)
        if runtime:
            try:
                health = run([runtime, "version"], timeout=min(15, remaining(deadline)), stdout_limit=65536)
            except (OSError, ValueError):
                continue
            if health.returncode == 0:
                return runtime
    return None


def run_scorecard(repository: str, output_path: Path, token: str | None = None,
                  timeout: int = 300, preferred_runtime: str | None = None,
                  allow_container: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout
    if token is None:
        token, source = discover_token()
    else:
        source = "provided in process memory"
    env = os.environ.copy()
    if token:
        env["GITHUB_AUTH_TOKEN"] = token
    args = ["--repo", f"github.com/{repository}", "--format", "json", "--show-details"]
    response = {"status": "unavailable", "executor": None, "token_source": source,
                "output_path": None, "error": None}
    try:
        local = shutil.which("scorecard")
        if local:
            response["executor"] = "local"
            response["executable"] = str(Path(local).resolve())
            with open(local, "rb") as executable:
                response["executable_sha256"] = hashlib.file_digest(executable, "sha256").hexdigest()
            result = run([local, *args], env=env, timeout=remaining(deadline))
        elif allow_container:
            runtime = working_runtime(preferred_runtime, deadline)
            if not runtime:
                raise RuntimeError("no container runtime is installed")
            response.update(executor=Path(runtime).name, image=SCORECARD_IMAGE)
            pull = run([runtime, "pull", SCORECARD_IMAGE], env=env, timeout=remaining(deadline))
            if pull.returncode:
                raise RuntimeError("Scorecard image pull failed")
            result = run_container(runtime, SCORECARD_IMAGE, args, env=env, timeout=remaining(deadline))
        else:
            response["error"] = "local Scorecard unavailable; explicit --allow-container approval required"
            return response
        if result.returncode:
            raise RuntimeError(_redact(result.stderr, token) or "Scorecard execution failed")
        json.loads(result.stdout)
        atomic_write_text(Path("/"), output_path.absolute().as_posix().lstrip("/"), _redact(result.stdout, token))
        response.update(status="success", output_path=str(output_path))
    except subprocess.TimeoutExpired:
        response.update(status="timed_out", error="Scorecard deadline exceeded; started work terminated")
    except (OSError, ValueError, RuntimeError) as exc:
        response.update(status="failed", error=_redact(str(exc), token))
    finally:
        response["duration_seconds"] = round(time.monotonic() - started, 3)
    return response


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--container-runtime")
    parser.add_argument("--allow-container", action="store_true")
    args = parser.parse_args(argv)
    response = run_scorecard(args.repo, args.output, timeout=args.timeout,
                            preferred_runtime=args.container_runtime, allow_container=args.allow_container)
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if response["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
