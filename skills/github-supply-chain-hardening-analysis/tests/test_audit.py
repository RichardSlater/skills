"""Offline regressions for supply-chain audit defects."""
import json
import importlib
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
discover_tokens = importlib.import_module("discover_tokens")
analyzer = importlib.import_module("gh_orchestrator")
scorecard_runner = importlib.import_module("scorecard_runner")


class AnalysisAuditTests(unittest.TestCase):
    def test_sequence_actions_and_multiline_shell_injection_are_detected(self):
        result = analyzer.AnalysisResult()
        analyzer._analyze_workflow(".github/workflows/test.yml", """permissions: read-all
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - run: |
          echo setup
          echo "${{ github.event.pull_request.title }}"
""", result)
        titles = {f.title for f in result.findings}
        self.assertIn("Mutable action reference", titles)
        self.assertIn("Untrusted GitHub context in shell command", titles)
        self.assertNotIn("Broad workflow permissions", titles)

    def test_nested_manifests_and_java_ecosystems_are_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested").mkdir()
            for name in ("package.json", "pom.xml", "build.gradle.kts"):
                (root / "nested" / name).write_text("{}")
            result = analyzer.analyze_repository(root, 1000)
            self.assertIn("npm/javascript", result.ecosystems)
            self.assertIn("maven/gradle", result.ecosystems)
            self.assertIn("nested/package.json", result.files_seen)

    def test_links_and_oversized_candidates_are_skipped_without_reading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root.parent / (root.name + "-outside")
            outside.write_text("private data")
            try:
                (root / ".env").symlink_to(outside)
                (root / "package.json").write_text("x" * 20)
                result = analyzer.analyze_repository(root, 10)
                self.assertFalse(result.scan["complete"])
                self.assertEqual(result.scan["skipped"], 2)
                self.assertIsNone(analyzer.read_text_limited(root / ".env", 100, root))
            finally:
                outside.unlink()

    def test_docker_tags_platforms_and_stage_aliases(self):
        result = analyzer.AnalysisResult()
        analyzer._analyze_dockerfile("Dockerfile", "FROM --platform=linux/amd64 python:3.12 AS build\nFROM build\nFROM scratch\nFROM alpine@sha256:" + "a" * 64, result)
        self.assertEqual(len(result.findings), 1)

    def test_unavailable_score_is_unknown_and_filename_not_critical(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "score.json"
            path.write_text(json.dumps({"checks": [{"name": "x", "score": -1}]}))
            self.assertEqual(analyzer.summarize_scorecard({"status": "success", "output_path": str(path)})["checks"][0]["derived_risk_rating"], "unknown")
        result = analyzer.AnalysisResult()
        analyzer._analyze_secret_indicators(".env.example", "EXAMPLE=placeholder", result)
        self.assertEqual(result.findings[0].risk, "medium")

    def test_expired_analysis_stops_before_inspection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.json").write_text("{}")
            with self.assertRaises(TimeoutError):
                analyzer.analyze_repository(root, 100, time.monotonic() - 1)

    def test_installation_token_is_valid_without_user_identity(self):
        token = discover_tokens.TokenCandidate("env", "not-a-real-token")
        with patch.object(discover_tokens, "_request", side_effect=[(403, {}, {}), (200, {}, {"repositories": [], "total_count": 0})]):
            result = discover_tokens.inspect_token(token, 100)
        self.assertTrue(result["valid"])
        self.assertEqual(result["token_type"], "GitHub App installation")
        self.assertIsNone(result["account"])

    def test_clone_environment_disables_ambient_filters_and_credentials(self):
        with patch.dict(os.environ, {"UNRELATED_SECRET": "do-not-forward"}):
            env, helper = analyzer._git_askpass_environment("test-token")
        try:
            self.assertNotIn("UNRELATED_SECRET", env)
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertEqual(env["GIT_LFS_SKIP_SMUDGE"], "1")
            self.assertNotIn("test-token", helper.read_text())
        finally:
            helper.unlink()

    def test_argument_tokens_are_rejected_without_echoing(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            analyzer.parse_args(["--org", "example", "--token", "never-echo-this-value"])
        self.assertNotIn("never-echo-this-value", output.getvalue())
        self.assertIn("forbidden", output.getvalue())

    def test_container_is_digest_pinned_and_requires_approval(self):
        self.assertIn("@sha256:", scorecard_runner.SCORECARD_IMAGE)
        with patch.object(scorecard_runner.shutil, "which", return_value=None):
            result = scorecard_runner.run_scorecard("a/b", Path("unused"), token="test")
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("test", result["error"])


if __name__ == "__main__":
    unittest.main()
