"""Regression tests for BadgeApp project identity verification (WP-03)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "analyze_best_practices.py"
spec = importlib.util.spec_from_file_location("analyze_identity", SCRIPT)
analyze = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(analyze)


class ProjectIdentityTests(unittest.TestCase):
    def test_url_variants_normalize_to_same_identity(self) -> None:
        expected = ("github.com", "owner", "repository")
        for url in (
            "https://github.com/Owner/Repository",
            "https://github.com/OWNER/repository.git/",
            "git@github.com:Owner/Repository.git",
            "ssh://git@github.com/Owner/Repository",
        ):
            self.assertEqual(analyze.normalize_github_repo_url(url), expected)

    def test_unrelated_readme_candidate_is_rejected(self) -> None:
        with patch.object(analyze, "fetch_project", return_value={"repo_url": "https://github.com/other/project"}):
            verified, rejected = analyze.verify_project_candidates({1}, "https://github.com/owner/repository")
        self.assertEqual(verified, [])
        self.assertEqual(rejected[0]["project_id"], 1)

    def test_same_owner_or_repository_alone_does_not_match(self) -> None:
        with patch.object(analyze, "fetch_project", side_effect=[
            {"repo_url": "https://github.com/owner/other"},
            {"repo_url": "https://github.com/other/repository"},
        ]):
            verified, rejected = analyze.verify_project_candidates({1, 2}, "https://github.com/owner/repository")
        self.assertEqual(verified, [])
        self.assertEqual([item["project_id"] for item in rejected], [1, 2])

    def test_malformed_credential_and_non_github_urls_are_rejected(self) -> None:
        for url in (
            "https://user:secret@github.com/owner/repository",
            "https://gitlab.com/owner/repository",
            "https://github.com/owner",
            "not a url",
        ):
            with self.assertRaises(ValueError):
                analyze.normalize_github_repo_url(url)

    def test_multiple_verified_candidates_remain_ambiguous(self) -> None:
        with patch.object(analyze, "fetch_project", return_value={"repo_url": "https://github.com/owner/repository"}):
            verified, rejected = analyze.verify_project_candidates({2, 1}, "https://github.com/owner/repository")
        self.assertEqual(verified, [1, 2])
        self.assertEqual(rejected, [])


if __name__ == "__main__":
    unittest.main()
