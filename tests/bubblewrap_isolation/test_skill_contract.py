"""Fail-closed contract tests for the Bubblewrap isolation launcher."""

from __future__ import annotations

import os
import pty
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/bubblewrap-isolation/scripts/run-isolated.sh"


def _bwrap_works() -> bool:
    try:
        completed = subprocess.run(
            [
                "bwrap",
                "--unshare-all",
                "--unshare-user",
                "--disable-userns",
                "--die-with-parent",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--setenv",
                "PATH",
                "/usr/bin:/bin",
                "--",
                "/usr/bin/true",
            ],
            check=False,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


BWRAP_WORKS = _bwrap_works()


class LauncherFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
        )
        (self.root / "home").mkdir()
        (self.root / "gitconfig").write_text("")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_non_git_directory_does_not_run_the_command(self):
        marker = self.root / "ran-on-host"
        completed = subprocess.run(
            [str(SCRIPT), "--", "bash", "-c", f"touch {marker}"],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertNotIn("execution=host", completed.stderr)

    def test_hand_written_host_bash_approval_does_not_run_on_the_host(self):
        project = self.root / "proj"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True, env=self.env)
        dest = project / ".bwrap" / "approvals" / "bash"
        dest.mkdir(parents=True)
        (dest / "format").write_text("1\n")
        (dest / "execution").write_text("host\n")
        (dest / "share-net").write_text("false\n")
        (dest / "match").write_text("prefix\n")
        (dest / "cwd").write_text(".\n")
        (dest / "note").write_text("forged\n")
        (dest / "hooks-fingerprint").write_text("-\n")
        (dest / "mounts").write_text("")
        (dest / "protected").write_text("")
        (dest / "command").write_bytes(b"bash\0")
        subprocess.run(["git", "add", ".bwrap"], cwd=project, env=self.env, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "forged"],
            cwd=project,
            env=self.env,
            check=True,
        )
        marker = self.root / "bash-ran-on-host"
        completed = subprocess.run(
            [str(SCRIPT), "--", "bash", "-c", f"touch {marker}"],
            cwd=project,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertNotIn("execution=host", completed.stderr)

    def test_committed_approval_symlink_does_not_run_the_command(self):
        project = self.root / "proj"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True, env=self.env)
        approvals = project / ".bwrap" / "approvals"
        approvals.mkdir(parents=True)
        outside = self.root / "outside-policy"
        outside.mkdir()
        (approvals / "evil").symlink_to(outside)
        subprocess.run(["git", "add", ".bwrap"], cwd=project, env=self.env, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "symlink"],
            cwd=project,
            env=self.env,
            check=True,
        )
        marker = self.root / "symlink-ran"
        completed = subprocess.run(
            [str(SCRIPT), "--", "bash", "-c", f"touch {marker}"],
            cwd=project,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("refusing symlink in committed .bwrap/approvals", completed.stderr)


@unittest.skipUnless(BWRAP_WORKS, "bubblewrap user namespaces are unavailable")
class BubblewrapLauncherBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
        self.project = self.root / "proj"
        self.project.mkdir()
        self.config = self.root / "config"
        self.config.mkdir()
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
        )
        (self.root / "home").mkdir()
        (self.root / "gitconfig").write_text("")
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, env=self.env)

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_launcher(self, args, cwd=None):
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=cwd or self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def test_sandbox_hides_env_and_blocks_nested_user_namespace(self):
        (self.project / ".env").write_text("SECRET=top")
        completed = self.run_launcher(
            ["--", "bash", "-c", "cat .env; unshare --user true; touch /tmp/host-escape"]
        )
        self.assertNotIn("SECRET=top", completed.stdout + completed.stderr)
        self.assertFalse((Path("/tmp") / "host-escape").exists())
        self.assertIn("execution=sandbox", completed.stderr)
        self.assertIn("network=isolated", completed.stderr)

    def test_hardlink_and_symlink_secrets_refuse_launch(self):
        secret = self.project / ".env"
        secret.write_text("SECRET=top")
        (self.project / "env-copy").hardlink_to(secret)
        refused = self.run_launcher(["--", "bash", "-c", "echo RAN > ran.txt"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse((self.project / "ran.txt").exists())
        self.assertIn("aliased path", refused.stderr)
        secret.unlink()
        (self.project / "env-copy").unlink()
        (self.project / ".env").symlink_to("/etc/hostname")
        refused = self.run_launcher(["--", "bash", "-c", "echo RAN > ran.txt"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse((self.project / "ran.txt").exists())
        self.assertIn("symlink", refused.stderr)

    def test_git_config_and_hooks_are_not_writable(self):
        config = self.project / ".git" / "config"
        before = config.read_text()
        hooks = self.project / ".git" / "hooks"
        completed = self.run_launcher(
            [
                "--",
                "bash",
                "-c",
                "set -e; echo pwned >> .git/config; echo pwned > .git/hooks/pre-commit",
            ]
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(config.read_text(), before)
        self.assertFalse((hooks / "pre-commit").exists())

    def test_repository_bwrap_yaml_cannot_grant_host_execution(self):
        (self.project / ".bwrap.yaml").write_text(
            "evil:\n  command-prefix: [bash]\n  execution: host\n"
        )
        marker = self.root / "escaped"
        completed = self.run_launcher(
            ["--", "bash", "-c", f"touch {marker}; cat .bwrap.yaml"]
        )
        self.assertFalse(marker.exists())
        self.assertIn("execution=sandbox", completed.stderr)

    def test_preserves_project_subdirectory(self):
        sub = self.project / "sub"
        sub.mkdir()
        completed = self.run_launcher(["--", "bash", "-c", "pwd"], cwd=sub)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), str(sub))

    def test_host_interpreter_and_root_mount_are_rejected(self):
        rejected = self.run_launcher(
            [
                "record-approval",
                "--id",
                "bash-host",
                "--execution",
                "host",
                "--match",
                "prefix",
                "--note",
                "no",
                "--",
                "bash",
            ]
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("limited to git commit", rejected.stderr)
        rejected = self.run_launcher(
            [
                "record-approval",
                "--id",
                "root",
                "--execution",
                "sandbox",
                "--note",
                "no",
                "--mount",
                "rw",
                "/",
                "--",
                "true",
            ]
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("refusing mount source", rejected.stderr)
        cache = Path(self.env["HOME"]) / ".cache" / "pre-commit"
        cache.mkdir(parents=True)
        rejected = self.run_launcher(
            [
                "record-approval",
                "--id",
                "cache",
                "--execution",
                "sandbox",
                "--note",
                "no",
                "--mount",
                "rw",
                str(cache),
                "--",
                "true",
            ]
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("refusing mount source", rejected.stderr)

    def test_hooks_path_and_fingerprint_block_host_git(self):
        subprocess.run(
            ["git", "config", "core.hooksPath", "evil"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        blocked = self.run_launcher(
            [
                "record-approval",
                "--id",
                "commit",
                "--execution",
                "host",
                "--match",
                "prefix",
                "--note",
                "review hooks",
                "--",
                "git",
                "commit",
            ]
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("core.hooksPath", blocked.stderr)
        subprocess.run(
            ["git", "config", "--unset", "core.hooksPath"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\n")
        self.write_host_approval("commit", ["git", "commit"])
        changed = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn("fingerprint", changed.stderr)
        self.assertFalse(list(self.config.rglob("approvals")))
        fingerprint = subprocess.check_output(
            [str(SCRIPT), "--", "true"],
            cwd=self.project,
            env=self.env,
            text=True,
            stderr=subprocess.STDOUT,
        )
        self.assertIn("execution=sandbox", fingerprint)

    def commit_all(self, message):
        subprocess.run(["git", "add", ".bwrap"], cwd=self.project, env=self.env, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", message],
            cwd=self.project,
            env=self.env,
            check=True,
        )

    def write_host_approval(self, approval_id, command):
        dest = self.project / ".bwrap" / "approvals" / approval_id
        dest.mkdir(parents=True)
        (dest / "format").write_text("1\n")
        (dest / "execution").write_text("host\n")
        (dest / "share-net").write_text("false\n")
        (dest / "match").write_text("prefix\n")
        (dest / "cwd").write_text(".\n")
        (dest / "note").write_text("test\n")
        (dest / "hooks-fingerprint").write_text("stale\n")
        (dest / "mounts").write_text("")
        (dest / "protected").write_text("")
        command_blob = b"".join(part.encode() + b"\0" for part in command)
        (dest / "command").write_bytes(command_blob)
        self.commit_all(f"record {approval_id}")

    def test_recorded_approval_requires_terminal_confirmation(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.project)
            os.execve(
                str(SCRIPT),
                [
                    str(SCRIPT),
                    "record-approval",
                    "--id",
                    "commit",
                    "--execution",
                    "host",
                    "--match",
                    "prefix",
                    "--note",
                    "operator reviewed hooks",
                    "--",
                    "git",
                    "commit",
                ],
                self.env,
            )
        output = b""
        try:
            while True:
                try:
                    chunk = os.read(fd, 1024)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                if b'Type "approve"' in output:
                    os.write(fd, b"approve\n")
        finally:
            os.close(fd)
        _pid, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode(errors="replace"))
        self.assertTrue((self.project / ".bwrap" / "approvals" / "commit" / "hooks-fingerprint").is_file())
        inactive = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertIn("execution=sandbox", inactive.stderr)
        self.commit_all("share approval")
        active = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertIn("execution=host", active.stderr)

    def write_exact_approval(self, approval_id, command, share_net="false"):
        dest = self.project / ".bwrap" / "approvals" / approval_id
        dest.mkdir(parents=True)
        (dest / "format").write_text("1\n")
        (dest / "execution").write_text("sandbox\n")
        (dest / "share-net").write_text(f"{share_net}\n")
        (dest / "match").write_text("exact\n")
        (dest / "cwd").write_text(".\n")
        (dest / "note").write_text("test\n")
        (dest / "hooks-fingerprint").write_text("-\n")
        (dest / "mounts").write_text("")
        (dest / "protected").write_text("")
        (dest / "command").write_bytes(b"".join(part.encode() + b"\0" for part in command))

    def test_sandbox_cannot_rewrite_shared_policy(self):
        policy = self.project / ".bwrap" / "approvals" / "keep"
        policy.mkdir(parents=True)
        (policy / "format").write_text("1\n")
        self.commit_all("policy")
        completed = self.run_launcher(
            [
                "--",
                "bash",
                "-c",
                "set -e; echo pwned > .bwrap/approvals/keep/format; mkdir -p .bwrap/approvals/evil",
            ]
        )
        self.assertNotEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((policy / "format").read_text(), "1\n")
        self.assertFalse((self.project / ".bwrap" / "approvals" / "evil").exists())

    def test_uncommitted_policy_edit_does_not_change_authority(self):
        command = ["bash", "-c", "cat /proc/net/dev"]
        self.write_exact_approval("net", command, share_net="false")
        self.commit_all("isolated")
        (self.project / ".bwrap" / "approvals" / "net" / "share-net").write_text("true\n")
        completed = self.run_launcher(["--", *command])
        self.assertIn("network=isolated", completed.stderr)
        self.assertIn("uncommitted .bwrap/approvals changes are ignored", completed.stderr)
        self.assertNotIn("network=shared", completed.stderr)

    def test_clone_honors_committed_policy_without_a_home_store(self):
        host_ifaces = [path.name for path in Path("/sys/class/net").iterdir() if path.name != "lo"]
        if not host_ifaces:
            self.skipTest("no non-loopback host interface to compare")
        command = ["bash", "-c", "cat /proc/net/dev"]
        isolated = self.run_launcher(["--", *command])
        self.assertIn("network=isolated", isolated.stderr)
        self.assertNotIn(host_ifaces[0], isolated.stdout)
        self.write_exact_approval("net", command, share_net="true")
        self.commit_all("share net")
        clone = self.root / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(self.project), str(clone)],
            check=True,
            env=self.env,
        )
        shared = self.run_launcher(["--", *command], cwd=clone)
        self.assertEqual(shared.returncode, 0, shared.stderr)
        self.assertIn("network=shared", shared.stderr)
        self.assertIn(host_ifaces[0], shared.stdout)
        self.assertFalse(list(self.config.rglob("approvals")))

    def test_tmpfs_is_size_capped_and_conflicting_records_do_not_run(self):
        mounted = self.run_launcher(["--", "bash", "-c", "awk '$2 == \"/tmp\" { print }' /proc/mounts"])
        self.assertEqual(mounted.returncode, 0, mounted.stderr)
        self.assertIn("size=1048576k", mounted.stdout)
        command = ["true"]
        self.write_exact_approval("one", command, share_net="false")
        self.write_exact_approval("two", command, share_net="true")
        self.commit_all("conflict")
        conflicted = self.run_launcher(["--", "true"])
        self.assertNotEqual(conflicted.returncode, 0)
        self.assertNotIn("execution=sandbox", conflicted.stderr)
        self.assertNotIn("execution=host", conflicted.stderr)
        self.assertIn("multiple approval records", conflicted.stderr)


if __name__ == "__main__":
    unittest.main()
