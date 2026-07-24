"""Static security checks for Scorecard PR reporting workflows."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = ROOT / ".github" / "workflows" / "scorecard-pr.yml"
COMMENT = ROOT / ".github" / "workflows" / "scorecard-pr-comment.yml"


class ScorecardReportingTests(unittest.TestCase):
    def test_analysis_remains_read_only_and_uploads_report(self) -> None:
        workflow = ANALYSIS.read_text(encoding="utf-8")
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("scorecard-pr-sarif", workflow)

    def test_commenter_has_narrow_permissions_and_no_checkout(self) -> None:
        workflow = COMMENT.read_text(encoding="utf-8")
        self.assertIn("workflow_run", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertNotIn("actions/checkout", workflow)
        self.assertIn("scorecard-pr-sarif", workflow)
        self.assertIn("scorecard-pr-summary", workflow)


if __name__ == "__main__":
    unittest.main()
