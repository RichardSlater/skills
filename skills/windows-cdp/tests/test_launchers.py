"""Offline launcher regression tests; no Windows processes are started."""

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin = Path(self.temp.name)
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": self.temp.name,
            "WINDOWS_CDP_EXE": str(self.bin / "chrome-devtools.exe"),
        }
        self.stub("chrome-devtools.exe", "printf '%s\\n' \"$@\"\n")
        self.stub("powershell.exe", "printf '%s\\n' \"$@\"\n")

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)

    def run_launcher(self, name, *args, port="9222", **env):
        return subprocess.run(
            [str(SCRIPTS / name), *args],
            env={**self.env, "WINDOWS_CDP_PORT": port, **env},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_launchers_are_executable(self):
        for name in ("windows-cdp", "windows-chrome"):
            self.assertTrue(os.access(SCRIPTS / name, os.X_OK), name)

    def test_invalid_ports_fail_before_interop(self):
        for name, args in (("windows-cdp", ("--help",)),
                           ("windows-chrome", ("status",))):
            for port in ("0", "00000", "65536", "-1", "x", "1+2",
                         "18446744073709560838", "0" * 100 + "8"):
                with self.subTest(name=name, port=port):
                    result = self.run_launcher(name, *args, port=port)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("invalid WINDOWS_CDP_PORT", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_cli_normalizes_decimal_ports(self):
        for port, expected in (("08", "8"), ("00008", "8"),
                               ("1", "1"), ("65535", "65535")):
            result = self.run_launcher("windows-cdp", "--help", port=port)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["--port", expected, "--help"])
            self.assertEqual(result.stderr, "")

    def test_cli_converts_windows_executable_paths(self):
        self.stub("wslpath", 'printf \'%s\\n\' "$HOME/chrome-devtools.exe"\n')
        for path in (r"C:\tools\chrome-devtools.exe", "C:/tools/chrome-devtools.exe"):
            with self.subTest(path=path):
                result = self.run_launcher("windows-cdp", "--help", WINDOWS_CDP_EXE=path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), ["--port", "9222", "--help"])

    def test_chrome_encodes_port_and_url_as_data(self):
        url = 'https://example.test/$(touch-not-code)?q="quoted"'
        result = self.run_launcher("windows-chrome", "start", url, port="08")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = base64.b64decode(result.stdout.splitlines()[-1]).decode("utf-16le")
        self.assertIn('-Action "start" -Port 8', command)
        self.assertIn(base64.b64encode(url.encode()).decode(), command)
        self.assertNotIn(url, command)

    def test_cli_requires_managed_browser(self):
        self.stub("powershell.exe", "echo 'managed browser unavailable' >&2; exit 9\n")
        result = self.run_launcher("windows-cdp", "list-pages")
        self.assertEqual(result.returncode, 9)
        self.assertIn("managed browser unavailable", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_help_with_global_options_needs_no_browser(self):
        self.stub("powershell.exe", "echo 'must not check browser' >&2; exit 9\n")
        result = self.run_launcher("windows-cdp", "--json", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_cli_recommends_only_approved_cargo_install(self):
        result = self.run_launcher("windows-cdp", "--help", WINDOWS_CDP_EXE="/missing")
        self.assertEqual(result.returncode, 127)
        self.assertNotIn("winget", result.stderr)
        self.assertIn("cargo install chrome-devtools-cli --version", result.stderr)
        self.assertIn("permission", result.stderr)

    def test_powershell_host_regressions(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
        if not powershell:
            self.skipTest("PowerShell is required for host regression tests")
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-File",
             str(Path(__file__).with_name("test_chrome_host.ps1"))],
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_endpoint_overrides_fail_before_browser_check(self):
        self.stub("powershell.exe", "exit 9\n")
        for flag in ("--port", "--ws-endpoint", "--user-data-dir"):
            result = self.run_launcher("windows-cdp", "list-pages", flag, "other")
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_double_dash_arguments_are_data(self):
        result = self.run_launcher("windows-cdp", "run-script", "test.js", "--", "--port=other")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], "--port=other")

    def test_long_encoded_command_is_refused(self):
        result = self.run_launcher("windows-chrome", "start", "https://example.test/" + "x" * 10000)
        self.assertEqual(result.returncode, 2)
        self.assertIn("command is too long", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_cli_refuses_endpoint_overrides(self):
        for flag in ("--port=1234", "--ws-endpoint=ws://elsewhere",
                     "--user-data-dir=other"):
            result = self.run_launcher("windows-cdp", "--help", flag)
            self.assertEqual(result.returncode, 2)
            self.assertIn("overrides are not allowed", result.stderr)
        result = self.run_launcher("windows-cdp", "--help", CHROME_WS_ENDPOINT="ws://other")
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing ambiguous", result.stderr)


if __name__ == "__main__":
    unittest.main()
