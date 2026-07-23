"""Regression tests for GitHub CLI account selection evidence."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"
spec = importlib.util.spec_from_file_location("github_auth", ROOT / "scripts" / "github_auth.py")
auth = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(auth)


class GitHubAuthTests(unittest.TestCase):
    def test_status_parser_excludes_token_values(self) -> None:
        accounts = auth.parse_status("""github.com
  ✓ Logged in to github.com account alice (/tmp/hosts.yml)
  - Active account: true
  - Token: gho_secret_value
  - Token scopes: 'repo', 'read:org'

  ✓ Logged in to github.com account bob (/tmp/hosts.yml)
  - Active account: false
  - Token scopes: 'gist'
""")
        self.assertEqual(
            accounts,
            [
                {"login": "alice", "active": True, "scopes": ["repo", "read:org"]},
                {"login": "bob", "active": False, "scopes": ["gist"]},
            ],
        )
        self.assertNotIn("gho_secret_value", str(accounts))

    def test_permission_query_and_unavailable_result(self) -> None:
        success = subprocess.CompletedProcess([], 0, "ADMIN\n", "")
        with patch.object(auth, "run", return_value=success) as run:
            self.assertEqual(auth.viewer_permission("owner/repo"), ("ADMIN", None))
        self.assertIn("graphql", run.call_args.args[0])
        with patch.object(auth, "run", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
            self.assertEqual(auth.viewer_permission("owner/repo"), (None, "unavailable"))
        with self.assertRaises(ValueError):
            auth.viewer_permission("https://github.com/owner/repo")

    def test_inventory_inspect_and_cli_paths(self) -> None:
        status = "✓ Logged in to github.com account alice\n  - Active account: true\n"
        with patch.object(auth, "run", return_value=subprocess.CompletedProcess([], 0, status, "")):
            self.assertEqual(auth.account_inventory("github.com"), [{"login": "alice", "active": True, "scopes": []}])
        with patch.object(auth, "run", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
            with self.assertRaisesRegex(RuntimeError, "unable to enumerate"):
                auth.account_inventory("github.com")
        with patch.object(auth, "account_inventory", return_value=[{"login": "alice", "active": True, "scopes": []}]), patch.object(auth, "viewer_permission", return_value=("WRITE", None)):
            self.assertEqual(
                auth.inspect("github.com", "owner/repo"),
                {"hostname": "github.com", "accounts": [{"login": "alice", "active": True, "scopes": []}], "active_account": "alice", "repository": "owner/repo", "active_viewer_permission": "WRITE"},
            )
        with patch("sys.argv", ["github_auth.py"]), patch.object(auth, "inspect", return_value={"accounts": []}), patch("builtins.print") as output:
            self.assertEqual(auth.main(), 0)
        self.assertIn('"accounts": []', output.call_args.args[0])
        with patch("sys.argv", ["github_auth.py"]), patch.object(auth, "inspect", side_effect=RuntimeError("blocked")), patch("builtins.print") as output:
            self.assertEqual(auth.main(), 3)
        self.assertEqual(output.call_args.args[0], "ERROR: blocked")


if __name__ == "__main__":
    unittest.main()
