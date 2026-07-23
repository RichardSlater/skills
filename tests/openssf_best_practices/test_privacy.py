"""Private repository disclosure regressions (WP-07)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import privacy
spec = importlib.util.spec_from_file_location("analyze_privacy", SCRIPTS / "analyze_best_practices.py")
analyze = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)

class PrivacyTests(unittest.TestCase):
    def test_private_disclosure_requires_destination_scoped_consent(self) -> None:
        with self.assertRaises(privacy.PrivacyError):
            privacy.disclosure_record({"isPrivate": True}, "bestpractices.dev", None)
        self.assertEqual({"destination": "bestpractices.dev", "scope": "current-repository-assessment"}, privacy.disclosure_record({"isPrivate": True}, "bestpractices.dev", "bestpractices.dev"))

    def test_private_discovery_makes_no_external_requests_without_consent(self) -> None:
        metadata = {"url": "https://github.com/private/repo", "isPrivate": True}
        with patch.object(analyze, "repo_metadata", return_value=metadata), patch.object(analyze, "tracked_text_files", return_value=[]), patch.object(analyze, "lookup_redirect") as lookup, patch.object(analyze, "verify_project_candidates") as candidates:
            result = analyze.discover_ids()
        lookup.assert_not_called(); candidates.assert_not_called()
        self.assertEqual(result["lookup"]["status"], "not_requested")

    def test_token_availability_is_not_consent(self) -> None:
        with self.assertRaises(privacy.PrivacyError):
            privacy.disclosure_record({"isPrivate": True, "token": "present"}, "scorecard", None)

    def test_public_repository_requires_no_consent(self) -> None:
        self.assertIsNone(privacy.disclosure_record({"isPrivate": False}, "scorecard", None))

if __name__ == "__main__": unittest.main()
