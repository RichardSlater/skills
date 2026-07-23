#!/usr/bin/env python3
"""Run a pinned OpenSSF Scorecard artifact under one total deadline."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_output import atomic_write_text
from privacy import PrivacyError, disclosure_record

# Deliberately reviewed immutable artifact. Update only with reviewed provenance.
SCORECARD_ARTIFACT = {
    "image": "ghcr.io/ossf/scorecard@sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795",
    "version": "v5.5.0",
    "digest": "sha256:3f24714e9366917adb7a05635382c97dfecb14b21eaef3dfa2ea48c8e23e0795",
}
RUNTIMES = ("podman", "docker", "nerdctl")
MAX_CAPTURE_BYTES = 64 * 1024


def _capture(value: str) -> str:
    return value if len(value.encode()) <= MAX_CAPTURE_BYTES else value.encode()[:MAX_CAPTURE_BYTES].decode(errors="replace") + "\n[TRUNCATED]"


def gh_token() -> str | None:
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError): return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def discover_token() -> tuple[str | None, str | None]:
    for name in ("GITHUB_AUTH_TOKEN", "GITHUB_TOKEN"):
        if value := os.environ.get(name, "").strip(): return value, name
    value = gh_token()
    return (value, "gh auth token") if value else (None, None)


def redact(value: str, token: str | None) -> str:
    return _capture(value.replace(token, "[REDACTED_TOKEN]")) if token else _capture(value)


def remaining(deadline: float, clock=time.monotonic) -> float:
    value = deadline - clock()
    if value <= 0: raise TimeoutError("shared Scorecard deadline exceeded")
    return value


def run_json(command: list[str], output: Path, env: dict[str, str], deadline: float, clock=time.monotonic) -> tuple[bool, str, bool]:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, check=False, timeout=remaining(deadline, clock))
        if result.returncode != 0: return False, _capture(result.stderr), False
        json.loads(result.stdout)
        atomic_write_text(output.parent.resolve(), output.name, result.stdout)
        return True, "", False
    except (subprocess.TimeoutExpired, TimeoutError): return False, "shared Scorecard deadline exceeded", True
    except (OSError, ValueError, json.JSONDecodeError) as exc: return False, str(exc), False


def working_runtime(preferred: str | None) -> list[str]:
    return [path for name in dict.fromkeys(x for x in ([preferred] if preferred else []) + list(RUNTIMES) if x) if (path := shutil.which(name))]


def result(status: str, started: float, clock, **values: Any) -> dict[str, Any]:
    return {"status": status, "provenance": {**SCORECARD_ARTIFACT, "started_monotonic": started, "finished_monotonic": clock(), "timeout_state": status == "timed_out"}, **values}


def execute(repository: str, output: Path, timeout: int, preferred: str | None, *, clock=time.monotonic) -> dict[str, Any]:
    started = clock(); deadline = started + timeout
    token, source = discover_token(); env = os.environ.copy()
    if token: env["GITHUB_AUTH_TOKEN"] = token
    args = ["--repo", f"github.com/{repository}", "--format", "json", "--show-details", "--show-annotations"]
    local = shutil.which("scorecard")
    if local:
        ok, error, timed_out = run_json([local, *args], output, env, deadline, clock)
        return result("success" if ok else "timed_out" if timed_out else "failed", started, clock, executor="scorecard", command_mode="local", token_source=source, output_path=str(output) if ok else None, error=redact(error, token) or None)
    errors: list[str] = []
    for runtime in working_runtime(preferred):
        name = Path(runtime).name
        try:
            pull = subprocess.run([runtime, "pull", SCORECARD_ARTIFACT["image"]], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=env, check=False, timeout=remaining(deadline, clock))
        except (subprocess.TimeoutExpired, TimeoutError):
            return result("timed_out", started, clock, executor=name, command_mode="container", token_source=source, output_path=None, error="shared Scorecard deadline exceeded")
        if pull.returncode != 0:
            errors.append(f"{name} pull: {redact(pull.stderr, token)}")
            continue
        command = [runtime, "run", "--rm"] + (["-e", "GITHUB_AUTH_TOKEN"] if token else []) + [SCORECARD_ARTIFACT["image"], *args]
        ok, error, timed_out = run_json(command, output, env, deadline, clock)
        if ok: return result("success", started, clock, executor=name, command_mode="container", token_source=source, output_path=str(output), error=None)
        if timed_out: return result("timed_out", started, clock, executor=name, command_mode="container", token_source=source, output_path=None, error=error)
        errors.append(f"{name} run: {redact(error, token)}")
    return result("failed", started, clock, executor=None, command_mode=None, token_source=source, output_path=None, error="; ".join(errors) or "No local Scorecard or working container runtime found.")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--repo", required=True); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--timeout", type=int, default=300); parser.add_argument("--container-runtime"); parser.add_argument("--private", action="store_true"); parser.add_argument("--private-consent", choices=("scorecard",)); args = parser.parse_args()
    try: disclosure_record({"isPrivate": args.private}, "scorecard", args.private_consent)
    except PrivacyError as exc: print(f"ERROR: {exc}", file=sys.stderr); return 2
    response = execute(args.repo, args.output, args.timeout, args.container_runtime); print(json.dumps(response, indent=2, sort_keys=True)); return 0 if response["status"] == "success" else 4 if response["status"] == "timed_out" else 3
if __name__ == "__main__": raise SystemExit(main())
