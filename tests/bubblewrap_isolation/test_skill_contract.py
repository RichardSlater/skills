"""Fail-closed contract tests for the Bubblewrap isolation launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/bubblewrap-isolation/scripts/run-isolated.sh"
SKILL = ROOT / "skills/bubblewrap-isolation/SKILL.md"


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
        self.assertFalse(marker.exists())
        self.assertNotIn("execution=host", completed.stderr)
        if completed.returncode == 0:
            self.assertIn("execution=sandbox", completed.stderr)
        self.assertFalse(list(project.rglob("hook-ran")))


@unittest.skipUnless(BWRAP_WORKS, "bubblewrap user namespaces are unavailable")
class BubblewrapLauncherBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(subprocess.check_output(["mktemp", "-d"], text=True).strip())
        self.project = self.root / "proj"
        self.project.mkdir()
        self.fake_home = self.root / "passwd-home"
        self.fake_home.mkdir()
        self.decoy_home = self.root / "decoy-home"
        decoy_config = self.decoy_home / ".config" / "bubblewrap-isolation"
        decoy_config.mkdir(parents=True)
        (decoy_config / "extra-commands").write_text("evil\n")
        (decoy_config / "network-commands").write_text("bash\n")
        (decoy_config / "host-commands").write_text("git commit\ngit push\n")
        self.passwd = self.root / "passwd"
        self.passwd.write_text(
            f"tester:x:{os.getuid()}:{os.getgid()}:Test:{self.fake_home}:/bin/bash\n"
        )
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.decoy_home),
                "XDG_CONFIG_HOME": str(self.decoy_home / ".config"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(self.root / "gitconfig"),
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
                "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
                "GNUPGHOME": str(self.fake_home / ".gnupg"),
            }
        )
        (self.root / "gitconfig").write_text("")
        (self.fake_home / ".gitconfig").write_text(
            "[user]\n\tname = Test\n\temail = test@example.com\n"
        )
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, env=self.env)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"

    def tearDown(self):
        shutil.rmtree(self.root)

    def config_dir(self):
        path = self.fake_home / ".config" / "bubblewrap-isolation"
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        return path

    def write_config(self, name, text):
        (self.config_dir() / name).write_text(text)

    def etc_overlay(self, resolv):
        etc = self.root / f"etc-{id(resolv)}"
        etc.mkdir()
        shutil.copy(self.passwd, etc / "passwd")
        (etc / "hosts").write_text("127.0.0.1 localhost\n")
        destination = etc / "resolv.conf"
        kind, value = resolv
        if kind == "file":
            destination.write_text(value)
        elif kind == "symlink":
            destination.symlink_to(value)
        else:
            raise AssertionError(kind)
        binds = ["--bind", str(etc), "/etc"]
        if Path("/etc/alternatives").is_dir():
            binds.extend(["--bind", "/etc/alternatives", "/etc/alternatives"])
        return binds

    def run_launcher(self, args, cwd=None, env=None, extra_bwrap=None):
        work = cwd or self.project
        command = [
            "bwrap",
            "--unshare-user",
            "--uid",
            str(os.getuid()),
            "--gid",
            str(os.getgid()),
            "--die-with-parent",
            "--bind",
            "/",
            "/",
            "--bind",
            str(self.passwd),
            "/etc/passwd",
            "--bind",
            str(self.fake_home),
            str(self.fake_home),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
        ]
        if extra_bwrap:
            command.extend(extra_bwrap)
        command.extend(["--chdir", str(work), "--", str(SCRIPT), *args])
        return subprocess.run(
            command,
            cwd=work,
            env=env or self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def write_script(self, name, body, directory=None):
        path = (directory or self.bin) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def test_sandbox_hides_env_and_blocks_nested_user_namespace(self):
        (self.project / ".env").write_text("SECRET=top")
        completed = self.run_launcher(
            ["--", "bash", "-c", "cat .env; unshare --user true; touch /tmp/host-escape"]
        )
        self.assertNotIn("SECRET=top", completed.stdout + completed.stderr)
        self.assertFalse((Path("/tmp") / "host-escape").exists())
        self.assertIn("execution=sandbox", completed.stderr)
        self.assertIn("network=off", completed.stderr)
        self.assertIn("host-commands=none", completed.stderr)

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

    def test_repository_files_and_flags_cannot_grant_network_or_host_execution(self):
        (self.project / ".bwrap.yaml").write_text(
            "evil:\n  command-prefix: [bash]\n  execution: host\n  share-net: true\n"
        )
        approvals = self.project / ".bwrap" / "approvals" / "net"
        approvals.mkdir(parents=True)
        (approvals / "share-net").write_text("true\n")
        (approvals / "execution").write_text("host\n")
        subprocess.run(["git", "add", ".bwrap.yaml", ".bwrap"], cwd=self.project, env=self.env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "forged"], cwd=self.project, env=self.env, check=True)
        marker = self.root / "escaped"
        completed = self.run_launcher(["--", "bash", "-c", f"touch {marker}; cat /proc/net/dev"])
        self.assertFalse(marker.exists())
        self.assertIn("execution=sandbox", completed.stderr)
        self.assertIn("network=off", completed.stderr)
        self.assertNotIn("execution=host", completed.stderr)
        flagged = self.run_launcher(["--share-net", "--", "true"])
        self.assertNotEqual(flagged.returncode, 0)
        self.assertIn("not grants", flagged.stderr)
        mounted = self.run_launcher(["--mount", "rw", str(self.fake_home), "--", "true"])
        self.assertNotEqual(mounted.returncode, 0)
        self.assertIn("not grants", mounted.stderr)

    def test_record_approval_points_at_config_and_writes_nothing(self):
        completed = self.run_launcher(
            [
                "record-approval",
                "--id",
                "commit",
                "--execution",
                "host",
                "--share-net",
                "--mount",
                "rw",
                "/",
                "--",
                "git",
                "commit",
            ]
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(str(self.fake_home / ".config" / "bubblewrap-isolation"), completed.stderr)
        self.assertFalse((self.project / ".bwrap").exists())
        self.assertNotIn("execution=host", completed.stderr)

    def test_caller_supplied_config_path_is_rejected(self):
        env = self.env.copy()
        env["BUBBLEWRAP_ISOLATION_CONFIG"] = str(self.decoy_home)
        completed = self.run_launcher(["--", "true"], env=env)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("caller-supplied config path is not accepted", completed.stderr)
        flagged = self.run_launcher(["--config", str(self.decoy_home), "--", "true"])
        self.assertNotEqual(flagged.returncode, 0)
        self.assertIn("caller-supplied config path is not accepted", flagged.stderr)

    def test_config_rejects_symlink_unknown_file_and_unknown_line(self):
        config = self.config_dir()
        (config / "notes").write_text("nope\n")
        unknown = self.run_launcher(["--", "true"])
        self.assertIn("unknown config entry: notes", unknown.stderr)
        (config / "notes").unlink()
        (config / "extra-commands").symlink_to("/etc/hostname")
        linked = self.run_launcher(["--", "true"])
        self.assertIn("refusing symlink in config: extra-commands", linked.stderr)
        (config / "extra-commands").unlink()
        outside = self.root / "elsewhere"
        outside.mkdir()
        config.rmdir()
        config.symlink_to(outside)
        linked_dir = self.run_launcher(["--", "true"])
        self.assertIn("refusing symlink in config path", linked_dir.stderr)
        config.unlink()
        self.write_config("host-commands", "pre-commit\n")
        bad_line = self.run_launcher(["--", "true"])
        self.assertIn("unknown line in host-commands: pre-commit", bad_line.stderr)
        self.assertNotIn("execution=host", bad_line.stderr)

    def test_preserves_project_subdirectory(self):
        sub = self.project / "sub"
        sub.mkdir()
        completed = self.run_launcher(["--", "bash", "-c", "pwd"], cwd=sub)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), str(sub))

    def test_local_path_is_prepended_and_visible_command_needs_no_list(self):
        completed = self.run_launcher(["--", "bash", "-c", 'printf %s "$PATH"'])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        path = completed.stdout
        if Path("/usr/local/bin").is_dir():
            self.assertTrue(path.startswith("/usr/local/bin:"), path)
        if Path("/usr/local/sbin").is_dir():
            self.assertIn("/usr/local/sbin:", path)
        visible = self.run_launcher(["--", "python3", "-c", "print(123)"])
        self.assertEqual(visible.returncode, 0, visible.stderr)
        self.assertIn("123", visible.stdout)
        self.assertIn("execution=sandbox", visible.stderr)
        self.assertNotIn("not in extra-commands", visible.stderr)

    def test_listed_command_binds_one_file_and_skips_the_project(self):
        self.write_script("evil", "echo EVIL\n")
        self.write_script("rg", 'echo OUTSIDE\nls "$(dirname "$0")"\n')
        project_bin = self.project / "bin"
        self.write_script("rg", "echo PROJECT\n", directory=project_bin)
        env = self.env.copy()
        env["PATH"] = f"{project_bin}:{self.bin}:/usr/bin:/bin"
        self.write_config("extra-commands", "rg\nmissing-tool\n")
        completed = self.run_launcher(["--", "rg"], env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("OUTSIDE", completed.stdout)
        self.assertNotIn("PROJECT", completed.stdout)
        self.assertNotIn("EVIL", completed.stdout)
        self.assertNotIn("evil", completed.stdout)
        self.assertIn("execution=sandbox", completed.stderr)
        self.assertIn("network=off", completed.stderr)
        unrelated = self.run_launcher(["--", "python3", "-c", "print('ok')"])
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertIn("ok", unrelated.stdout)

    def test_unlisted_and_unavailable_commands_do_not_run_on_the_host(self):
        marker = self.root / "evil-ran"
        self.write_script("evil", f"touch {marker}\n")
        missing = self.run_launcher(["--", "evil"])
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("not in extra-commands: evil", missing.stderr)
        self.assertFalse(marker.exists())
        self.assertNotIn("execution=host", missing.stderr)
        self.assertNotIn("execution=sandbox", missing.stderr)
        self.write_config("extra-commands", "evil\n")
        (self.bin / "evil").unlink()
        unavailable = self.run_launcher(["--", "evil"])
        self.assertIn("not available: evil", unavailable.stderr)
        self.assertFalse(marker.exists())
        self.write_script("evil", "echo RAN\n")
        link = self.bin / "linkevil"
        link.symlink_to(self.bin / "evil")
        env = self.env.copy()
        env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.write_config("extra-commands", "linkevil\n")
        # PATH lookup of linkevil finds the symlink first.
        linked = self.run_launcher(["--", "linkevil"], env=env)
        self.assertIn("not available: linkevil", linked.stderr)
        self.assertNotIn("execution=host", linked.stderr)

    def test_closure_refusals_are_not_available(self):
        target = self.write_script("rg", "echo RAN\n")
        hard = self.bin / "rg-hard"
        hard.hardlink_to(target)
        env = self.env.copy()
        env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.write_config("extra-commands", "rg-hard\n")
        refused = self.run_launcher(["--", "rg-hard"], env=env)
        self.assertIn("not available: rg-hard", refused.stderr)
        cred = self.fake_home / ".ssh"
        cred.mkdir()
        self.write_script("rg", "echo CRED\n", directory=cred)
        env["PATH"] = f"{cred}:/usr/bin:/bin"
        self.write_config("extra-commands", "rg\n")
        refused = self.run_launcher(["--", "rg"], env=env)
        self.assertIn("not available: rg", refused.stderr)
        outside = self.root / "interp"
        outside.mkdir()
        self.write_script("badinterp", "echo NO\n", directory=self.bin)
        (self.bin / "badinterp").write_text(f"#!{outside}/python\necho NO\n")
        (self.bin / "badinterp").chmod(0o755)
        env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.write_config("extra-commands", "badinterp\n")
        refused = self.run_launcher(["--", "badinterp"], env=env)
        self.assertIn("not available: badinterp", refused.stderr)
        elf = self.bin / "elftrue"
        shutil.copy("/usr/bin/true", elf)
        elf.chmod(0o755)
        self.write_config("extra-commands", "elftrue\n")
        accepted = self.run_launcher(["--", "elftrue"], env=env)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("execution=sandbox", accepted.stderr)

    def test_network_is_per_command_and_does_not_mount_host_config(self):
        host_ifaces = [path.name for path in Path("/sys/class/net").iterdir() if path.name != "lo"]
        if not host_ifaces:
            self.skipTest("no non-loopback host interface to compare")
        self.write_script("rg", "cat /proc/net/dev\n")
        self.write_script("pnpm", "cat /proc/net/dev\n")
        self.write_config("extra-commands", "rg\npnpm\n")
        self.write_config("network-commands", "pnpm install\n")
        (self.fake_home / ".npmrc").write_text("NPMRC_SECRET\n")
        cargo = self.fake_home / ".cargo"
        cargo.mkdir()
        (cargo / "config.toml").write_text("CARGO_SECRET\n")
        cache = self.fake_home / ".cache" / "pre-commit"
        cache.mkdir(parents=True)
        (cache / "poison").write_text("CACHE_SECRET\n")
        ssh = self.fake_home / ".ssh"
        ssh.mkdir()
        (ssh / "id").write_text("SSH_SECRET\n")
        offline = self.run_launcher(["--", "rg"])
        self.assertIn("network=off", offline.stderr)
        self.assertNotIn(host_ifaces[0], offline.stdout)
        self.assertNotIn("network=on", offline.stderr)
        allowed_etc = self.etc_overlay(("file", "nameserver 127.0.0.1\n"))
        installed = self.run_launcher(
            ["--", "pnpm", "install", "--frozen-lockfile"],
            extra_bwrap=allowed_etc,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertIn("network=on", installed.stderr)
        self.assertIn(host_ifaces[0], installed.stdout)
        published = self.run_launcher(["--", "pnpm", "publish"])
        self.assertIn("network=off", published.stderr)
        self.assertNotIn(host_ifaces[0], published.stdout)
        probe = (
            f"echo HOME=$HOME; cat {self.fake_home}/.npmrc || true; "
            f"cat {cargo}/config.toml || true; cat {cache}/poison || true; "
            f"cat {ssh}/id || true; env | grep SSH_AUTH_SOCK || true"
        )
        hidden = self.run_launcher(
            ["--", "pnpm", "install", "--", "ignored"],
            extra_bwrap=allowed_etc,
        )
        self.assertIn("network=on", hidden.stderr)
        leaked = self.run_launcher(["--", "bash", "-c", probe])
        self.assertIn("network=off", leaked.stderr)
        self.assertIn("HOME=/tmp/bwrap-home", leaked.stdout)
        self.assertNotIn("NPMRC_SECRET", leaked.stdout)
        self.assertNotIn("CARGO_SECRET", leaked.stdout)
        self.assertNotIn("CACHE_SECRET", leaked.stdout)
        self.assertNotIn("SSH_SECRET", leaked.stdout)
        self.assertNotIn("SSH_AUTH_SOCK", leaked.stdout)

    def test_host_commands_are_exact_and_keep_credentials_out_of_sandbox(self):
        self.write_config("host-commands", "git commit\n")
        self.write_config("network-commands", "git push\n")
        marker = self.project / "hook-ran"
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\necho RAN > {marker}\nexit 0\n")
        hook.chmod(0o755)
        (self.project / "file").write_text("x\n")
        subprocess.run(["git", "add", "file"], cwd=self.project, env=self.env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.project, env=self.env, check=True)
        marker.unlink(missing_ok=True)
        (self.project / "file2").write_text("y\n")
        subprocess.run(["git", "add", "file2"], cwd=self.project, env=self.env, check=True)
        committed = self.run_launcher(["--", "git", "commit", "-m", "via-host"])
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.assertIn("execution=host", committed.stderr)
        self.assertIn("network=host", committed.stderr)
        self.assertIn("host-commands=git commit", committed.stderr)
        self.assertTrue(marker.is_file())
        marker.unlink()
        pushed = self.run_launcher(["--", "git", "push"])
        self.assertNotEqual(pushed.returncode, 0)
        self.assertIn("not in host-commands: git push", pushed.stderr)
        self.assertNotIn("execution=host", pushed.stderr)
        self.assertNotIn("execution=sandbox", pushed.stderr)
        self.assertFalse(marker.exists())
        status = self.run_launcher(["--", "git", "status", "--short"])
        self.assertIn("execution=sandbox", status.stderr)
        self.assertNotIn("execution=host", status.stderr)
        self.write_script("pre-commit", f"touch {self.root}/pre-commit-host\n")
        precommit = self.run_launcher(["--", "pre-commit", "--version"])
        self.assertNotIn("execution=host", precommit.stderr)
        self.assertFalse((self.root / "pre-commit-host").exists())
        sandboxed = self.run_launcher(
            ["--", "bash", "-c", f"echo HOME=$HOME; cat {self.fake_home}/.ssh/id || true; env"]
        )
        self.assertIn("execution=sandbox", sandboxed.stderr)
        self.assertIn("HOME=/tmp/bwrap-home", sandboxed.stdout)
        self.assertNotIn("SSH_AUTH_SOCK", sandboxed.stdout)
        self.assertIn("host-commands=git commit", sandboxed.stderr)

    def test_missing_host_command_runs_neither_host_nor_sandbox(self):
        marker = self.project / "hook-ran"
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\necho RAN > {marker}\n")
        hook.chmod(0o755)
        completed = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not in host-commands: git commit", completed.stderr)
        self.assertNotIn("execution=host", completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)
        self.assertFalse(marker.exists())

    def test_hooks_path_and_symlinked_hook_block_host_git(self):
        self.write_config("host-commands", "git commit\n")
        subprocess.run(
            ["git", "config", "core.hooksPath", "evil"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        blocked = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("core.hooksPath", blocked.stderr)
        self.assertNotIn("execution=host", blocked.stderr)
        self.assertNotIn("execution=sandbox", blocked.stderr)
        subprocess.run(
            ["git", "config", "--unset", "core.hooksPath"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.symlink_to("/bin/true")
        blocked = self.run_launcher(["--", "git", "commit", "-m", "x"])
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("symlinked hook", blocked.stderr)
        self.assertNotIn("execution=sandbox", blocked.stderr)

    def test_sandbox_cannot_rewrite_bwrap_and_tmpfs_is_capped(self):
        policy = self.project / ".bwrap" / "approvals" / "keep"
        policy.mkdir(parents=True)
        (policy / "format").write_text("1\n")
        subprocess.run(["git", "add", ".bwrap"], cwd=self.project, env=self.env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "policy"], cwd=self.project, env=self.env, check=True)
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
        mounted = self.run_launcher(["--", "bash", "-c", "awk '$2 == \"/tmp\" { print }' /proc/mounts"])
        self.assertEqual(mounted.returncode, 0, mounted.stderr)
        self.assertIn("size=1048576k", mounted.stdout)

    def test_inherited_git_dir_does_not_redirect_host_commit(self):
        self.write_config("host-commands", "git commit\n")
        other = self.root / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True, env=self.env)
        other_marker = self.root / "other-hook"
        other_hook = other / ".git" / "hooks" / "pre-commit"
        other_hook.write_text(f"#!/bin/sh\necho OTHER > {other_marker}\nexit 0\n")
        other_hook.chmod(0o755)
        env_file = self.root / "commit-env"
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\nenv > {env_file}\nexit 0\n")
        hook.chmod(0o755)
        (self.project / "tracked").write_text("a\n")
        subprocess.run(["git", "add", "tracked"], cwd=self.project, env=self.env, check=True)
        env = self.env.copy()
        env["GIT_DIR"] = str(other / ".git")
        env["GIT_WORK_TREE"] = str(other)
        env["GIT_SSH_COMMAND"] = "evil-ssh-command-marker"
        completed = self.run_launcher(["--", "git", "commit", "-m", "project-commit"], env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("execution=host", completed.stderr)
        self.assertFalse(other_marker.exists())
        self.assertTrue(env_file.is_file())
        recorded = env_file.read_text()
        self.assertNotIn("evil-ssh-command-marker", recorded)
        self.assertNotIn(str(other / ".git"), recorded)
        self.assertIn(f"HOME={self.fake_home}", recorded)
        self.assertIn("USER=tester", recorded)
        self.assertNotIn("GNUPGHOME=", recorded)
        log = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"],
            cwd=self.project,
            env=self.env,
            text=True,
        )
        self.assertEqual(log.strip(), "project-commit")
        other_log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=other,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(other_log.stdout.strip(), "project-commit")

    def test_inherited_git_ssh_command_is_not_forwarded(self):
        self.write_config("host-commands", "git push\n")
        (self.project / "tracked").write_text("a\n")
        subprocess.run(["git", "add", "tracked"], cwd=self.project, env=self.env, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True, env=self.env)
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote)],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        env_file = self.root / "push-env"
        hook = self.project / ".git" / "hooks" / "pre-push"
        hook.write_text(f"#!/bin/sh\nenv > {env_file}\nexit 0\n")
        hook.chmod(0o755)
        sock = self.root / "agent.sock"
        subprocess.run(["python3", "-c", f"import socket; s=socket.socket(socket.AF_UNIX); s.bind('{sock}')"], check=True)
        env = self.env.copy()
        env["GIT_SSH_COMMAND"] = "evil-ssh-command-marker"
        env["SSH_AUTH_SOCK"] = str(sock)
        env["GNUPGHOME"] = str(self.fake_home / ".gnupg")
        completed = self.run_launcher(["--", "git", "push", "origin", "HEAD"], env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("execution=host", completed.stderr)
        recorded = env_file.read_text()
        self.assertNotIn("evil-ssh-command-marker", recorded)
        self.assertNotIn("GIT_SSH_COMMAND=", recorded)
        self.assertNotIn("GNUPGHOME=", recorded)
        self.assertIn(f"SSH_AUTH_SOCK={sock}", recorded)
        self.assertIn(f"HOME={self.fake_home}", recorded)

    def test_repository_ssh_command_refuses_host_push(self):
        self.write_config("host-commands", "git push\n")
        marker = self.root / "ssh-command-ran"
        subprocess.run(
            ["git", "config", "core.sshCommand", f"touch {marker}"],
            cwd=self.project,
            env=self.env,
            check=True,
        )
        completed = self.run_launcher(["--", "git", "push"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("core.sshCommand", completed.stderr)
        self.assertNotIn("execution=host", completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)
        self.assertFalse(marker.exists())

    def test_project_containing_home_is_refused(self):
        subprocess.run(["git", "init", "-q", str(self.fake_home)], check=True, env=self.env)
        marker = self.fake_home / "ran"
        home_root = self.run_launcher(
            ["--", "bash", "-c", f"touch {marker}"],
            cwd=self.fake_home,
        )
        self.assertNotEqual(home_root.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("contains the invoking user's home", home_root.stderr)
        self.assertNotIn("execution=sandbox", home_root.stderr)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, env=self.env)
        ancestor_marker = self.root / "ancestor-ran"
        ancestor = self.run_launcher(
            ["--", "bash", "-c", f"touch {ancestor_marker}"],
            cwd=self.root,
        )
        self.assertNotEqual(ancestor.returncode, 0)
        self.assertFalse(ancestor_marker.exists())
        self.assertIn("contains the invoking user's home", ancestor.stderr)

    def test_nested_env_files_are_unreadable(self):
        nested = self.project / "nested"
        nested.mkdir()
        (nested / ".env").write_text("SECRET=nested\n")
        (nested / ".envrc").write_text("SECRET=rc\n")
        (nested / ".env.example").write_text("SECRET=example\n")
        completed = self.run_launcher(
            ["--", "bash", "-c", "cat nested/.env nested/.envrc nested/.env.example"]
        )
        self.assertNotIn("SECRET=", completed.stdout + completed.stderr)
        self.assertNotIn("execution=host", completed.stderr)

    def test_project_ssh_directory_refuses_launch(self):
        (self.project / ".ssh").mkdir()
        (self.project / ".ssh" / "id").write_text("KEY\n")
        marker = self.project / "ran"
        completed = self.run_launcher(["--", "bash", "-c", f"echo RAN > {marker}"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("credential directory", completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)

    def test_failed_hardlink_walk_refuses_launch(self):
        self.write_script("find", "echo scan-failed >&2\nexit 1\n")
        marker = self.project / "ran"
        completed = self.run_launcher(["--", "bash", "-c", f"echo RAN > {marker}"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("hardlink scan failed", completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)

    def test_group_writable_config_refuses_without_changing_mode(self):
        missing = self.fake_home / ".config" / "bubblewrap-isolation"
        self.assertFalse(missing.exists())
        untouched = self.run_launcher(["--", "true"])
        self.assertEqual(untouched.returncode, 0, untouched.stderr)
        self.assertFalse(missing.exists())
        config = self.config_dir()
        host_commands = config / "host-commands"
        host_commands.write_text("git commit\n")
        host_commands.chmod(0o664)
        marker = self.project / "ran"
        completed = self.run_launcher(["--", "bash", "-c", f"echo RAN > {marker}"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("group- or other-writable operator config", completed.stderr)
        self.assertEqual(host_commands.stat().st_mode & 0o777, 0o664)
        self.assertNotIn("execution=sandbox", completed.stderr)

    def test_unparsed_elf_is_not_available(self):
        elf = self.bin / "badelf"
        elf.write_bytes(b"\x7fELF")
        elf.chmod(0o755)
        self.write_config("extra-commands", "badelf\n")
        completed = self.run_launcher(["--", "badelf"])
        self.assertIn("not available: badelf", completed.stderr)
        self.assertNotIn("execution=host", completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)

    def test_resolver_under_home_refuses_network_command(self):
        target = self.fake_home / "resolv.conf"
        target.write_text("nameserver 9.9.9.9\n")
        self.write_config("network-commands", "bash\n")
        marker = self.project / "ran"
        completed = self.run_launcher(
            ["--", "bash", "-c", f"echo RAN > {marker}"],
            extra_bwrap=self.etc_overlay(("symlink", str(target))),
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertIn("refusing resolver path", completed.stderr)
        self.assertIn(str(target), completed.stderr)
        self.assertNotIn("execution=sandbox", completed.stderr)

    def test_run_resolver_stub_is_copied_without_mounting_run(self):
        run_root = self.root / "fake-run"
        stub_dir = run_root / "systemd" / "resolve"
        stub_dir.mkdir(parents=True)
        (stub_dir / "stub-resolv.conf").write_text("nameserver 127.0.0.53\nSTUBMARK\n")
        self.write_config("network-commands", "bash\n")
        completed = self.run_launcher(
            [
                "--",
                "bash",
                "-c",
                "cat /etc/resolv.conf; test ! -e /run/systemd/resolve/stub-resolv.conf",
            ],
            extra_bwrap=[
                *self.etc_overlay(("symlink", "/run/systemd/resolve/stub-resolv.conf")),
                "--bind",
                str(run_root),
                "/run",
            ],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("STUBMARK", completed.stdout)
        self.assertIn("network=on", completed.stderr)
        self.assertNotIn("/run/systemd/resolve/stub-resolv.conf", completed.stdout)

    def test_skill_reports_errors_instead_of_approvals(self):
        text = SKILL.read_text()
        front = text.split("---", 2)[1]
        body = text.split("---", 2)[2]
        self.assertIn("Network is off unless", front)
        self.assertIn("network-commands", front)
        self.assertNotIn("no network", front.lower())
        self.assertIn("Network is off unless", body)
        self.assertIn("network-commands", body)
        self.assertIn("not in extra-commands: <name>", text)
        self.assertIn("not available: <name>", text)
        self.assertIn("not in host-commands: git commit", text)
        self.assertIn("not in host-commands: git push", text)
        self.assertIn("network=off", text)
        self.assertIn("host-commands=", text)
        self.assertIn("Do not ask the operator to approve", text)
        self.assertNotIn("record-approval \\", text)
        self.assertIn("record-approval` does not record anything", text)
        self.assertIn("global pre-commit cache", text)
        self.assertIn("disposable environment", text)


if __name__ == "__main__":
    unittest.main()
