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


if __name__ == "__main__":
    unittest.main()
