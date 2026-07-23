"""Section-aware, bounded proposal URL regressions (WP-09)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

spec = importlib.util.spec_from_file_location("analyze_proposals", Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "analyze_best_practices.py")
analyze = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)

class ProposalTests(unittest.TestCase):
    def test_unknown_and_wrong_section_are_rejected(self):
        with self.assertRaises(ValueError): analyze.proposal_url(1, "passing", {"invented_status": "Met"})
        with self.assertRaises(ValueError): analyze.proposal_url(1, "gold", {"floss_license_status": "Met"})
    def test_long_proposal_does_not_emit_url(self):
        proposal = {"floss_license_status": "Met", "floss_license_justification": "x" * 70_000}
        with self.assertRaises(analyze.ProposalTooLong): analyze.proposal_url(1, "passing", proposal)
    def test_exact_limit_succeeds_and_one_over_fails(self):
        original = analyze.MAX_PROPOSAL_URL_LENGTH
        try:
            base = analyze.proposal_url(1, "passing", {"floss_license_status": "Met"})
            analyze.MAX_PROPOSAL_URL_LENGTH = len(base)
            self.assertEqual(analyze.proposal_url(1, "passing", {"floss_license_status": "Met"}), base)
            analyze.MAX_PROPOSAL_URL_LENGTH = len(base) - 1
            with self.assertRaises(analyze.ProposalTooLong): analyze.proposal_url(1, "passing", {"floss_license_status": "Met"})
        finally: analyze.MAX_PROPOSAL_URL_LENGTH = original
    def test_unicode_and_reserved_characters_round_trip(self):
        url = analyze.proposal_url(1, "passing", {"floss_license_status": "Met", "floss_license_justification": "é & = ✓"})
        self.assertEqual(parse_qs(urlparse(url).query)["floss_license_justification"], ["é & = ✓"])

if __name__ == "__main__": unittest.main()
