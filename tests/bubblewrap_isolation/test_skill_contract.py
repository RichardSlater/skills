"""Fail-closed contract tests for the Bubblewrap isolation launcher."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import unittest
from pathlib import Path

import yaml


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


class ResolverPolicyTests(unittest.TestCase):
    """Exercise the real policy function without requiring nested namespaces."""

    def resolver_allowed(self, path, **metadata):
        source = SCRIPT.read_text()
        policy = source.split("resolver_target_allowed() {", 1)[1].split(
            "\ncopy_network_files() {", 1
        )[0]
        script = "resolver_target_allowed() {" + policy
        script += """
REAL_HOME=/home/tester
in_forbidden_bind_dir() { [[ "$1" == /forbidden/* ]]; }
path_has_symlink_component() { [[ "$1" == "${SYMLINK_PATH:-}" ]]; }
stat() {
  case "${@: -1}" in
    /mnt) printf '%s\\n' "$MNT_STAT" ;;
    /mnt/wsl) printf '%s\\n' "$WSL_STAT" ;;
    /mnt/wsl/resolv.conf) printf '%s\\n' "$RESOLVER_STAT" ;;
    *) return 1 ;;
  esac
}
resolver_target_allowed "$1"
"""
        env = os.environ.copy()
        env.update(
            MNT_STAT="0:755:2",
            WSL_STAT="0:1777:2",
            RESOLVER_STAT="0:644:1",
        )
        env.update(metadata)
        completed = subprocess.run(
            ["bash", "-c", script, "resolver-policy", path],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        self.assertIn(completed.returncode, (0, 1), completed.stderr)
        return completed.returncode == 0

    def test_root_owned_wsl_resolver_is_allowed(self):
        self.assertTrue(self.resolver_allowed("/mnt/wsl/resolv.conf"))

    def test_wsl_exception_does_not_allow_other_paths(self):
        for path in (
            "/mnt/wsl/secret",
            "/mnt/wsl/resolv.conf.backup",
            "/mnt/other/resolv.conf",
            "/home/tester/resolv.conf",
            "/forbidden/resolv.conf",
        ):
            with self.subTest(path=path):
                self.assertFalse(self.resolver_allowed(path))

    def test_unsafe_wsl_resolver_metadata_is_rejected(self):
        for metadata in (
            {"RESOLVER_STAT": "1000:644:1"},
            {"RESOLVER_STAT": "0:664:1"},
            {"RESOLVER_STAT": "0:646:1"},
            {"RESOLVER_STAT": "0:644:2"},
            {"RESOLVER_STAT": ""},
            {"MNT_STAT": "1000:755:2"},
            {"MNT_STAT": "0:777:2"},
            {"WSL_STAT": "1000:1777:2"},
            {"WSL_STAT": "0:777:2"},
            {"SYMLINK_PATH": "/mnt/wsl/resolv.conf"},
        ):
            with self.subTest(metadata=metadata):
                self.assertFalse(
                    self.resolver_allowed("/mnt/wsl/resolv.conf", **metadata)
                )

    def test_existing_system_resolver_locations_remain_allowed(self):
        self.assertTrue(self.resolver_allowed("/etc/resolv.conf"))
        self.assertTrue(self.resolver_allowed("/run/systemd/resolve/stub-resolv.conf"))


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
        (decoy_config / "config.yml").write_text(
            yaml.safe_dump(
                {
                    "global": {
                        "extra": ["evil"],
                        "network": ["bash"],
                        "host": ["git commit", "git push"],
                    }
                }
            )
        )
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

    def write_config(self, name, text, project=None):
        keys = {
            "extra-commands": "extra",
            "network-commands": "network",
            "host-commands": "host",
            "package-managers": "package_managers",
        }
        key = keys[name]
        path = self.config_dir() / "config.yml"
        data = {"global": {}}
        if path.exists() and not path.is_symlink():
            loaded = yaml.safe_load(path.read_text()) or {}
            if isinstance(loaded, dict):
                data = loaded
        if not isinstance(data.get("global"), dict):
            data["global"] = {}
        items = text.splitlines()
        if project is None:
            data["global"][key] = items
        else:
            projects = data.get("projects")
            if not isinstance(projects, list):
                projects = []
                data["projects"] = projects
            block = next(
                (
                    item
                    for item in projects
                    if isinstance(item, dict) and item.get("path") == project
                ),
                None,
            )
            if block is None:
                block = {"path": project}
                projects.append(block)
            block[key] = items
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        path.chmod(0o600)

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
        (config / "config.yml").symlink_to("/etc/hostname")
        linked = self.run_launcher(["--", "true"])
        self.assertIn("refusing symlink in config: config.yml", linked.stderr)
        (config / "config.yml").unlink()
        outside = self.root / "elsewhere"
        outside.mkdir()
        config.rmdir()
        config.symlink_to(outside)
        linked_dir = self.run_launcher(["--", "true"])
        self.assertIn("refusing symlink in config path", linked_dir.stderr)
        config.unlink()
        self.write_config("host-commands", "sudo\n")
        bad_line = self.run_launcher(["--", "true"])
        self.assertIn("unknown line in host-commands: sudo", bad_line.stderr)
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

    def test_package_managers_expose_prepared_tools_read_only(self):
        self.write_script("node", "echo NODE_RUNTIME\n")
        (self.fake_home / ".npmrc").write_text("PRIVATE_NPM_CONFIG\n")
        for manager in ("uv", "npm", "pnpm", "cargo", "bun", "deno", "pip"):
            with self.subTest(manager=manager):
                env = self.env.copy()
                if manager == "uv":
                    tool_bin = self.fake_home / ".local/share/uv/tools/demo/bin"
                    tool_bin.mkdir(parents=True)
                    tool = tool_bin / "managed-demo"
                    self.write_script("uv", "echo UV_MANAGER\n")
                elif manager == "pnpm":
                    tool_bin = self.fake_home / ".local/share/pnpm"
                    tool_bin.mkdir(parents=True)
                    tool = tool_bin / "managed-demo"
                    self.write_script("pnpm", "echo PNPM_MANAGER\n")
                elif manager in ("cargo", "bun", "deno"):
                    tool_bin = self.fake_home / f".{manager}/bin"
                    tool_bin.mkdir(parents=True)
                    tool = tool_bin / "managed-demo"
                    if manager == "cargo":
                        self.write_script("rustup", "echo CARGO_MANAGER\n", directory=tool_bin)
                        (tool_bin / "cargo").symlink_to("rustup")
                    else:
                        self.write_script(manager, f"echo {manager.upper()}_MANAGER\n", directory=tool_bin)
                    env["PATH"] = f"{tool_bin}:{self.env['PATH']}"
                elif manager == "pip":
                    tool_bin = self.fake_home / ".local/bin"
                    tool_bin.mkdir(parents=True)
                    tool = tool_bin / "managed-demo"
                    site = self.fake_home / ".local/lib/python3.13/site-packages"
                    metadata = site / "demo-1.0.dist-info"
                    metadata.mkdir(parents=True)
                    (metadata / "entry_points.txt").write_text(
                        "[console_scripts]\nmanaged-demo = demo:main\n"
                    )
                    self.write_script("pip", "echo PIP_MANAGER\n")
                    self.write_script("unrelated", "echo NOT_A_PIP_TOOL\n", directory=tool_bin)
                else:
                    prefix = self.fake_home / ".nvm/versions/node/test"
                    tool_bin = prefix / "bin"
                    tool_bin.mkdir(parents=True)
                    cli = prefix / "lib/node_modules/npm/bin/npm-cli.js"
                    cli.parent.mkdir(parents=True)
                    cli.write_text("#!/bin/sh\necho NPM_MANAGER\n")
                    cli.chmod(0o755)
                    (tool_bin / "npm").symlink_to(cli)
                    tool = tool_bin / "managed-demo"
                    env["PATH"] = f"{tool_bin}:{self.env['PATH']}"
                dependency = tool_bin / "package-data"
                if manager == "pip":
                    dependency = site / "package-data"
                elif manager == "bun":
                    dependency = self.fake_home / ".bun/install/global/package-data"
                elif manager == "deno":
                    dependency = self.fake_home / ".cache/deno/package-data"
                dependency.parent.mkdir(parents=True, exist_ok=True)
                dependency.write_text(f"{manager}_DEPENDENCY\n")
                tool.write_text(
                    f"#!/bin/sh\ncat {dependency}\n"
                    f"if test -e {self.fake_home}/.npmrc; then echo EXPOSED_CONFIG; fi\n"
                    f"if test -e {self.fake_home}/.local/bin/unrelated; then echo EXPOSED_BIN; fi\n"
                    f"if echo changed > {dependency}; then echo WRITABLE_PACKAGE; fi\n"
                )
                tool.chmod(0o755)
                self.write_config("package-managers", manager + "\n")
                manager_run = self.run_launcher(["--", manager, "--version"], env=env)
                self.assertEqual(manager_run.returncode, 0, manager_run.stderr)
                self.assertIn(f"{manager.upper()}_MANAGER", manager_run.stdout)
                completed = self.run_launcher(["--", "managed-demo"], env=env)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(f"{manager}_DEPENDENCY", completed.stdout)
                self.assertNotIn("EXPOSED_CONFIG", completed.stdout)
                self.assertNotIn("EXPOSED_BIN", completed.stdout)
                self.assertNotIn("WRITABLE_PACKAGE", completed.stdout)
                self.assertIn("execution=sandbox network=off", completed.stderr)
                self.assertEqual(dependency.read_text(), f"{manager}_DEPENDENCY\n")

    def test_pip_console_script_imports_user_site_packages(self):
        version = subprocess.check_output(
            ["/usr/bin/python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            text=True,
        ).strip()
        site = self.fake_home / f".local/lib/python{version}/site-packages"
        metadata = site / "demo-1.0.dist-info"
        metadata.mkdir(parents=True)
        (site / "pip_demo.py").write_text("def main(): print('PIP_IMPORT_OK')\n")
        (metadata / "entry_points.txt").write_text("[console_scripts]\npip-demo = pip_demo:main\n")
        tool = self.fake_home / ".local/bin/pip-demo"
        tool.parent.mkdir(parents=True)
        tool.write_text("#!/usr/bin/python3\nfrom pip_demo import main\nmain()\n")
        tool.chmod(0o755)
        self.write_script("pip", "echo PIP\n")
        self.write_config("package-managers", "pip\n")
        completed = self.run_launcher(["--", "pip-demo"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("PIP_IMPORT_OK", completed.stdout)
        self.assertIn("execution=sandbox network=off", completed.stderr)

    def test_unknown_package_manager_is_rejected(self):
        self.write_config("package-managers", "yarn\n")
        completed = self.run_launcher(["--", "true"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unknown line in package-managers: yarn", completed.stderr)
        self.assertNotIn("execution=", completed.stderr)

    def test_package_managed_tool_requires_opt_in(self):
        path = self.fake_home / ".local/share/pnpm"
        self.write_script("managed-demo", "echo RAN\n", directory=path)
        env = self.env.copy()
        env["PATH"] = f"{path}:{self.env['PATH']}"
        completed = self.run_launcher(["--", "managed-demo"], env=env)
        self.assertIn("not in extra-commands: managed-demo", completed.stderr)
        self.assertNotIn("execution=", completed.stderr)

    def test_arbitrary_host_prefix_scrubs_environment_and_project_path(self):
        self.write_config("host-commands", "some-tool --check\n")
        self.write_script("some-tool", 'printf "ARGS:%s:%s\\n" "$1" "$2"\nenv\n')
        project_bin = self.project / "bin"
        self.write_script("some-tool", "echo PROJECT_EXECUTABLE\n", directory=project_bin)
        env = self.env.copy()
        env["PATH"] = f"{project_bin}:{self.env['PATH']}"
        env["INHERITED_SECRET"] = "must-not-leak"
        with socket.socket(socket.AF_UNIX) as agent:
            sock = self.root / "agent.sock"
            agent.bind(str(sock))
            env["SSH_AUTH_SOCK"] = str(sock)
            for argument in ("later", "push"):
                with self.subTest(argument=argument):
                    completed = self.run_launcher(
                        ["--", "some-tool", "--check", argument], env=env
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertIn(f"ARGS:--check:{argument}", completed.stdout)
                    self.assertIn(f"HOME={self.fake_home}", completed.stdout)
                    self.assertIn("USER=tester", completed.stdout)
                    self.assertIn(f"PATH={self.env['PATH']}", completed.stdout)
                    self.assertNotIn(str(project_bin), completed.stdout)
                    self.assertNotIn("PROJECT_EXECUTABLE", completed.stdout)
                    for key in ("SSH_AUTH_SOCK=", "GNUPGHOME=", "GIT_CONFIG_GLOBAL=",
                                "INHERITED_SECRET=", "must-not-leak"):
                        self.assertNotIn(key, completed.stdout)
                    self.assertIn("execution=host network=host", completed.stderr)
                    self.assertIn("host-commands=some-tool --check command=", completed.stderr)

    def test_pre_commit_host_grant_is_explicit_and_uses_normal_host_controls(self):
        self.write_script("pre-commit", 'printf "ARG:%s\\n" "$1"\nenv\n')
        self.write_config("extra-commands", "pre-commit\n")
        self.write_config("host-commands", "pre-commit run\n")
        env = self.env.copy()
        env["INHERITED_SECRET"] = "must-not-leak"
        completed = self.run_launcher(
            ["--", "pre-commit", "run", "--all-files"], env=env
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ARG:run", completed.stdout)
        self.assertIn(f"HOME={self.fake_home}", completed.stdout)
        self.assertNotIn("INHERITED_SECRET=", completed.stdout)
        self.assertNotIn("SSH_AUTH_SOCK=", completed.stdout)
        self.assertIn("execution=host network=host", completed.stderr)
        self.assertIn("host-commands=pre-commit run command=", completed.stderr)

        for argument in ("--version", "runner"):
            with self.subTest(argument=argument):
                unmatched = self.run_launcher(["--", "pre-commit", argument])
                # The sandbox may resolve its installed pre-commit rather than
                # our host stub; dispatch must not depend on that tool's result.
                self.assertIn("execution=sandbox network=off", unmatched.stderr)
        self.write_config("host-commands", "")
        unlisted = self.run_launcher(["--", "pre-commit", "--version"])
        self.assertEqual(unlisted.returncode, 0, unlisted.stderr)
        self.assertIn("execution=sandbox network=off", unlisted.stderr)

        self.write_config("host-commands", "pre-commit\n")
        broad = self.run_launcher(["--", "pre-commit", "--version"])
        self.assertEqual(broad.returncode, 0, broad.stderr)
        self.assertIn("execution=host network=host", broad.stderr)
        canary = self.run_launcher(["--", "true"])
        self.assertEqual(canary.returncode, 0, canary.stderr)
        self.assertIn("execution=sandbox", canary.stderr)

        subprocess.run(
            ["git", "config", "core.hooksPath", "/tmp/other-hooks"],
            cwd=self.project, env=self.env, check=True,
        )
        refused = self.run_launcher(["--", "pre-commit", "run"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn("execution=host", refused.stderr)

    def test_project_grant_does_not_apply_to_another_project(self):
        self.write_script("pre-commit", 'printf "ARG:%s\\n" "$1"\n')
        self.write_config("extra-commands", "pre-commit\n")
        self.write_config("host-commands", "git commit\n")
        project = os.path.realpath(self.project)
        self.write_config("host-commands", "pre-commit run\n", project=project)
        granted = self.run_launcher(["--", "pre-commit", "run", "--all-files"])
        self.assertEqual(granted.returncode, 0, granted.stderr)
        self.assertIn("ARG:run", granted.stdout)
        self.assertIn("execution=host network=host", granted.stderr)
        self.assertIn("host-commands=git commit,pre-commit run command=", granted.stderr)

        other = self.root / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True, env=self.env)
        unmatched = self.run_launcher(["--", "pre-commit", "run"], cwd=other)
        self.assertIn("execution=sandbox network=off", unmatched.stderr)
        self.assertIn("host-commands=git commit command=", unmatched.stderr)
        self.assertNotIn("host-commands=git commit,pre-commit run", unmatched.stderr)

    def test_config_yml_rejects_old_files_and_noncanonical_paths(self):
        self.write_config("host-commands", "git commit\n")
        old = self.config_dir() / "extra-commands"
        old.write_text("rg\n")
        rejected = self.run_launcher(["--", "true"])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unknown config entry: extra-commands", rejected.stderr)
        self.assertNotIn("execution=", rejected.stderr)
        old.unlink()
        alias = self.config_dir() / "config.yaml"
        alias.write_text("global: {}\n")
        rejected = self.run_launcher(["--", "true"])
        self.assertIn("unknown config entry: config.yaml", rejected.stderr)
        alias.unlink()

        relative = self.config_dir() / "config.yml"
        relative.write_text("projects:\n  - path: relative\n    host: ['true']\n")
        relative.chmod(0o600)
        rejected = self.run_launcher(["--", "true"])
        self.assertIn("config path is not canonical: relative", rejected.stderr)
        self.assertNotIn("execution=", rejected.stderr)

        path = os.path.realpath(self.project)
        duplicate = (
            "projects:\n"
            f"  - path: {path}\n"
            "    host: ['git commit']\n"
            f"  - path: {path}\n"
            "    host: ['git push']\n"
        )
        relative.write_text(duplicate)
        relative.chmod(0o600)
        rejected = self.run_launcher(["--", "true"])
        self.assertIn(f"duplicate project path: {path}", rejected.stderr)
        self.assertNotIn("execution=", rejected.stderr)

    def test_host_lines_refuse_forbidden_first_tokens_and_malformed_prefixes(self):
        lines = [f"{name} --check" for name in (
            "bwrap", "sudo", "su", "sudoedit", "pkexec", "doas", "unshare",
            "chroot", "nsenter", "systemd-run", "machinectl", "lxc-attach",
            "docker", "podman", "crun", "runc", "proot", "setpriv", "capsh",
            "newuidmap", "newgidmap", "fakeroot", "nix", "nix-shell",
            "bash", "sh", "dash", "zsh", "fish", "python", "python3",
            "perl", "ruby", "node", "env", "busybox", "timeout", "nohup",
            "stdbuf", "nice", "ionice", "setsid", "script", "ssh", "scp",
            "sftp", "gpg",
        )]
        lines += ["some-tool /tmp/file", "some-tool  --check", " some-tool",
                  "some-tool ", "some-tool\t--check", "some-tool 'two words'",
                  "some-tool --", "some-tool;true"]
        for line in lines:
            with self.subTest(line=line):
                self.write_config("host-commands", line + "\n")
                completed = self.run_launcher(["--", "true"])
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(f"unknown line in host-commands: {line}", completed.stderr)
                self.assertNotIn("execution=", completed.stderr)

    def test_unlisted_push_runs_nowhere_and_unmatched_prefix_stays_sandboxed(self):
        self.write_config("host-commands", "some-tool --check\n")
        push = self.run_launcher(["--", "git", "push"])
        self.assertNotEqual(push.returncode, 0)
        self.assertIn("not in host-commands: git push", push.stderr)
        self.assertNotIn("execution=", push.stderr)
        self.write_config("extra-commands", "some-tool\n")
        self.write_script("some-tool", 'printf "ARG:%s\\n" "$1"\n')
        for arg in ("--fix", "--checker"):
            with self.subTest(arg=arg):
                completed = self.run_launcher(["--", "some-tool", arg])
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(f"ARG:{arg}", completed.stdout)
                self.assertIn("execution=sandbox network=off", completed.stderr)
        self.write_config("host-commands", "")
        unlisted = self.run_launcher(["--", "some-tool", "--check"])
        self.assertEqual(unlisted.returncode, 0, unlisted.stderr)
        self.assertIn("execution=sandbox", unlisted.stderr)
        self.assertIn("host-commands=none", unlisted.stderr)

    def test_long_option_network_prefix_uses_exact_tokens(self):
        self.write_script("some-tool", "echo RAN\n")
        self.write_config("extra-commands", "some-tool\n")
        self.write_config("network-commands", "some-tool --check\n")
        resolver = self.etc_overlay(("file", "nameserver 127.0.0.1\n"))
        for args, network in ((["--check", "later"], "on"), (["--checker"], "off")):
            with self.subTest(args=args):
                completed = self.run_launcher(
                    ["--", "some-tool", *args],
                    extra_bwrap=resolver,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(f"execution=sandbox network={network}", completed.stderr)
        self.write_config("network-commands", "some-tool --\n")
        refused = self.run_launcher(["--", "true"])
        self.assertIn("unknown line in network-commands: some-tool --", refused.stderr)
        self.assertNotIn("execution=", refused.stderr)

    def test_host_summary_preserves_file_order_and_deduplicates(self):
        self.write_config(
            "host-commands",
            "git push\nsome-tool --check\ngit commit\nsome-tool --check\ngit push\n",
        )
        completed = self.run_launcher(["--", "true"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "host-commands=git push,some-tool --check,git commit command=",
            completed.stderr,
        )

    def test_bare_host_prefix_matches_later_arguments(self):
        self.write_script("some-tool", 'printf "ARG:%s\\n" "$1"\n')
        self.write_config("host-commands", "some-tool\n")
        completed = self.run_launcher(["--", "some-tool", "--check"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("execution=host", completed.stderr)
        self.assertIn("ARG:--check", completed.stdout)
        self.write_config("host-commands", "git\n")
        git = self.run_launcher(["--", "git", "status", "--short"])
        self.assertEqual(git.returncode, 0, git.stderr)
        self.assertIn("execution=host", git.stderr)

    def test_arbitrary_host_command_checks_metadata_and_executable(self):
        self.write_config("host-commands", "some-tool\n")
        target = self.write_script("some-tool", "echo RAN\n")
        subprocess.run(
            ["git", "config", "core.hooksPath", "evil"],
            cwd=self.project, env=self.env, check=True,
        )
        blocked = self.run_launcher(["--", "some-tool"])
        self.assertIn("core.hooksPath", blocked.stderr)
        self.assertNotIn("execution=", blocked.stderr)
        subprocess.run(
            ["git", "config", "--unset", "core.hooksPath"],
            cwd=self.project, env=self.env, check=True,
        )
        real = target.with_name("real-tool")
        target.rename(real)
        target.symlink_to(real)
        linked = self.run_launcher(["--", "some-tool"])
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("refusing host executable", linked.stderr)
        self.assertNotIn("execution=", linked.stderr)
        target.unlink()
        self.write_script("some-tool", "echo PROJECT\n", directory=self.project / "bin")
        env = self.env.copy()
        env["PATH"] = f"{self.project / 'bin'}:/usr/bin:/bin"
        project_only = self.run_launcher(["--", "some-tool"], env=env)
        self.assertIn("refusing host executable", project_only.stderr)
        self.assertNotIn("execution=", project_only.stderr)

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
        host_commands = config / "config.yml"
        host_commands.write_text("global:\n  host: [git commit]\n")
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


    def test_refused_host_name_still_runs_in_the_sandbox(self):
        completed = self.run_launcher(["--", "python3", "-c", "print('SANDBOX_PYTHON')"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("SANDBOX_PYTHON", completed.stdout)
        self.assertIn("execution=sandbox", completed.stderr)

    def test_npm_home_prefix_exposes_modules_not_home_secrets(self):
        cli = self.fake_home / "lib/node_modules/npm/bin/npm-cli.js"
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/bin/sh\necho NPM_OK\n")
        cli.chmod(0o755)
        bin_dir = self.fake_home / "bin"
        bin_dir.mkdir()
        (bin_dir / "npm").symlink_to("../lib/node_modules/npm/bin/npm-cli.js")
        dependency = self.fake_home / "lib/node_modules/demo-data"
        dependency.write_text("NPM_DEPENDENCY\n")
        tool = bin_dir / "managed-demo"
        tool.write_text(f"#!/bin/sh\ncat {dependency}\n")
        tool.chmod(0o755)
        (self.fake_home / ".ssh").mkdir()
        (self.fake_home / ".ssh/id").write_text("SECRET_KEY\n")
        (self.fake_home / ".npmrc").write_text("SECRET_NPMRC\n")
        self.write_script("node", "echo NODE\n")
        self.write_config("package-managers", "npm\n")
        env = self.env.copy()
        env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        npm_run = self.run_launcher(["--", "npm", "--version"], env=env)
        self.assertEqual(npm_run.returncode, 0, npm_run.stderr)
        self.assertIn("NPM_OK", npm_run.stdout)
        tool_run = self.run_launcher(["--", "managed-demo"], env=env)
        self.assertEqual(tool_run.returncode, 0, tool_run.stderr)
        self.assertIn("NPM_DEPENDENCY", tool_run.stdout)
        probe = self.run_launcher(
            ["--", "bash", "-c", f"cat {self.fake_home}/.ssh/id {self.fake_home}/.npmrc || true"],
            env=env,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertNotIn("SECRET_KEY", probe.stdout)
        self.assertNotIn("SECRET_NPMRC", probe.stdout)
        self.assertIn("execution=sandbox", probe.stderr)

    def test_symlinked_package_root_preserves_interior_symlink(self):
        real = self.fake_home / "real-cargo-bin"
        real.mkdir()
        (real / "package-data").write_text("CARGO_SYMLINK\n")
        target = real / "real-tool"
        target.write_text(f"#!/bin/sh\ncat {real}/package-data\n")
        target.chmod(0o755)
        (real / "managed-demo").symlink_to("real-tool")
        cargo = self.fake_home / ".cargo"
        cargo.mkdir()
        (cargo / "bin").symlink_to(real)
        self.write_script("cargo", "echo CARGO\n")
        self.write_config("package-managers", "cargo\n")
        completed = self.run_launcher(["--", "managed-demo"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("CARGO_SYMLINK", completed.stdout)
        self.assertIn("execution=sandbox", completed.stderr)

    def test_package_root_symlink_to_home_is_refused(self):
        cargo = self.fake_home / ".cargo"
        cargo.mkdir()
        (cargo / "bin").symlink_to(self.fake_home)
        (self.fake_home / ".ssh").mkdir()
        (self.fake_home / ".ssh/id").write_text("SECRET_KEY\n")
        self.write_script("cargo", "echo CARGO\n")
        self.write_config("package-managers", "cargo\n")
        completed = self.run_launcher(["--", "true"])
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("overly broad", completed.stderr)
        self.assertNotIn("SECRET_KEY", completed.stdout)
        self.assertNotIn("execution=", completed.stderr)

    def test_pnpm_bin_is_visible_when_pnpm_is_outside_its_home(self):
        home = self.fake_home / ".local/share/pnpm"
        tool_bin = home / "bin"
        tool_bin.mkdir(parents=True)
        dependency = home / "package-data"
        dependency.write_text("PNPM_BIN_DEPENDENCY\n")
        tool = tool_bin / "managed-demo"
        tool.write_text(f"#!/bin/sh\ncat {dependency}\n")
        tool.chmod(0o755)
        self.write_script("pnpm", "echo PNPM\n")
        self.write_script("node", "echo NODE\n")
        self.write_config("package-managers", "pnpm\n")
        completed = self.run_launcher(["--", "managed-demo"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("PNPM_BIN_DEPENDENCY", completed.stdout)
        self.assertIn("execution=sandbox", completed.stderr)

    def test_missing_manager_does_not_fail_unrelated_commands(self):
        if Path("/usr/bin/deno").exists() or Path("/bin/deno").exists():
            self.skipTest("host deno would satisfy the missing-manager fixture")
        self.write_config("package-managers", "deno\n")
        unrelated = self.run_launcher(["--", "true"])
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertIn("execution=sandbox", unrelated.stderr)
        missing = self.run_launcher(["--", "deno", "--version"])
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("not available: deno", missing.stderr)
        self.assertNotIn("execution=", missing.stderr)

    def test_missing_node_does_not_fail_unrelated_commands(self):
        self.write_script("npm", "echo NPM\n")
        self.write_config("package-managers", "npm\n")
        hidden = self.root / "not-executable"
        hidden.write_text("")
        hidden.chmod(0o644)
        hide_node = ["--ro-bind", str(hidden), "/usr/bin/node", "--ro-bind", str(hidden), "/bin/node"]
        unrelated = self.run_launcher(["--", "true"], extra_bwrap=hide_node)
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        self.assertIn("execution=sandbox", unrelated.stderr)
        missing = self.run_launcher(["--", "npm", "--version"], extra_bwrap=hide_node)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("not available: node", missing.stderr)
        self.assertNotIn("execution=", missing.stderr)


if __name__ == "__main__":
    unittest.main()
