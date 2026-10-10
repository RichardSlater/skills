"""Bounded POSIX subprocesses with process-group and container cleanup."""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
import uuid

MAX_STDOUT = 16 * 1024 * 1024
MAX_STDERR = 64 * 1024


def run(command, *, env=None, timeout=300, stdout_limit=MAX_STDOUT):
    """Capture bounded bytes, kill and reap the whole group on any failure."""
    if os.name != "posix" or timeout <= 0:
        raise ValueError("bounded execution requires POSIX and a positive timeout")
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, start_new_session=True)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        with selectors.DefaultSelector() as selector:
            for name in buffers:
                selector.register(getattr(process, name), selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command[0], timeout)
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    limit = stdout_limit if key.data == "stdout" else MAX_STDERR
                    if len(buffers[key.data]) + len(data) > limit:
                        raise ValueError("subprocess output limit exceeded")
                    buffers[key.data].extend(data)
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, process.returncode,
            buffers["stdout"].decode("utf-8", errors="replace"),
            buffers["stderr"].decode("utf-8", errors="replace"))
    finally:
        # Also remove descendants that survived a normally exiting parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


def run_container(runtime, image, arguments, *, env, timeout):
    """Use an unguessable name so a daemon-side job can always be removed."""
    name = "skill-scorecard-" + uuid.uuid4().hex
    command = [runtime, "run", "--rm", "--name", name]
    if env.get("GITHUB_AUTH_TOKEN"):
        command += ["-e", "GITHUB_AUTH_TOKEN"]
    command += [image, *arguments]
    try:
        return run(command, env=env, timeout=timeout)
    finally:
        cleanup = run([runtime, "rm", "--force", name], env=env, timeout=15)
        if cleanup.returncode and not any(word in cleanup.stderr.lower()
                for word in ("no such container", "not found", "does not exist")):
            raise RuntimeError("container cleanup failed; operator intervention required")
