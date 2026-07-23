"""Evidence-gap and BadgeApp summary regression tests (WP-05)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "analyze_best_practices.py"
spec = importlib.util.spec_from_file_location("analyze_summary", SCRIPT)
analyze = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(analyze)

class SummaryTests(unittest.TestCase):
    def test_gold_level_and_current_timestamps_are_preserved(self) -> None:
        data = {"id": 1, "repo_url": "https://github.com/owner/repository", "badge_level": "gold", "achieved_passing_at": "2020-01-01", "achieved_silver_at": "2021-01-01", "achieved_gold_at": "2022-01-01"}
        summary = analyze.project_summary(data)
        self.assertEqual(summary["badge_level"], "gold")
        self.assertEqual(summary["achieved_gold_at"], "2022-01-01")

    def test_optional_timestamps_remain_null(self) -> None:
        summary = analyze.project_summary({"id": 1, "repo_url": "https://github.com/owner/repository", "badge_level": "passing"})
        self.assertIsNone(summary["achieved_silver_at"])
        self.assertEqual(summary["badge_level"], "passing")

    def test_mismatched_identity_fails_before_summary(self) -> None:
        with self.assertRaises(ValueError):
            analyze.validate_project_response({"id": 1, "repo_url": "https://github.com/other/repository"}, "https://github.com/owner/repository")

if __name__ == "__main__": unittest.main()
