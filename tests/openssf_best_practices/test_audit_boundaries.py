"""Integration regressions for audit consent, confinement and cancellation."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills/openssf-best-practices/scripts"
sys.path.insert(0, str(SCRIPTS))
import bounded_process
import privacy
import safe_files
import safe_output


def load(name):
    spec = importlib.util.spec_from_file_location("audit_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyze = load("analyze_best_practices")
scorecard = load("scorecard_runner")
snapshot = load("assessment_snapshot")


class AuditBoundaryTests(unittest.TestCase):
    def test_default_discovery_is_offline_and_candidates_unverified(self):
        meta = {"nameWithOwner": "a/b", "url": "https://github.com/a/b", "isPrivate": None}
        with patch.object(analyze, "local_repo_metadata", return_value=meta), patch.object(analyze, "tracked_text_files", return_value=[]), patch.object(analyze, "repo_metadata") as remote, patch.object(analyze, "lookup_redirect") as lookup:
            result = analyze.discover_ids()
        remote.assert_not_called()
        lookup.assert_not_called()
        self.assertEqual(result["verification_state"], "not_requested")

    def test_consent_binds_repository_and_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "consent.json"
            record.write_text(json.dumps({"repository": "a/b", "scope": "assessment-disclosure", "destinations": ["scorecard"]}))
            self.assertEqual(privacy.require_disclosure(record, "a/b", "scorecard")["repository"], "a/b")
            for repository, destination in (("other/b", "scorecard"), ("a/b", "github")):
                with self.assertRaises(privacy.PrivacyError):
                    privacy.require_disclosure(record, repository, destination)
            with self.assertRaises(privacy.PrivacyError):
                privacy.require_disclosure(None, "a/b", "scorecard")
            record.write_text(json.dumps({"repository": "a/b", "scope": "assessment-disclosure", "destinations": "scorecard"}))
            with self.assertRaises(privacy.PrivacyError):
                privacy.require_disclosure(record, "a/b", "scorecard")
            record.write_text("invalid")
            with self.assertRaises(privacy.PrivacyError):
                privacy.require_disclosure(record, "a/b", "scorecard")

    def test_linked_output_parent_is_rejected_by_public_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "outside").mkdir()
            (root / "linked").symlink_to(root / "outside", target_is_directory=True)
            with self.assertRaises(safe_output.UnsafePathError):
                analyze.write_json(root / "linked/result.json", {})
            self.assertFalse((root / "outside/result.json").exists())

    def test_cli_output_requires_approval_and_ignore_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("reports/\n")
            approval = Path(temp) / "approval.json"
            approval.write_text(json.dumps({"scope": "apply", "repository": str(root), "allowed_paths": ["reports/x.json"]}))
            (root / "reports").mkdir()
            def run(command):
                return subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
            with patch.object(analyze, "run", side_effect=run):
                with self.assertRaises(ValueError):
                    analyze.write_json(root / "reports/x.json", {})
                analyze.write_json(root / "reports/x.json", {}, approval)
                with self.assertRaises(ValueError):
                    analyze.write_json(root / "other.json", {}, approval)
            self.assertEqual(json.loads((root / "reports/x.json").read_text()), {})

    def test_unreadable_or_oversized_discovery_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "big.md").write_bytes(b"x" * (analyze.MAX_SCAN_FILE_BYTES + 1))
            _, _, meta = analyze.scan_project_ids([Path("missing.md"), Path("big.md")], root=root)
            self.assertTrue(meta["limits_hit"])

    def test_safe_reader_rejects_links_hardlinks_specials_and_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "file").write_bytes(b"abc")
            self.assertEqual(safe_files.read_bytes(root, Path("file"), 3), b"abc")
            (root / "link").symlink_to(root / "file")
            os.mkfifo(root / "fifo")
            for name in ("link", "fifo"):
                with self.assertRaises((ValueError, OSError)):
                    safe_files.read_bytes(root, Path(name), 10)
            with self.assertRaises(ValueError):
                safe_files.read_bytes(root, Path("file"), 2)
            os.link(root / "file", root / "hard")
            with self.assertRaises(ValueError):
                safe_files.read_bytes(root, Path("hard"), 10)
            with self.assertRaises(ValueError):
                safe_files.read_bytes(root, Path("../file"), 10)

    def test_bounded_process_success_failure_output_limit_and_timeout(self):
        self.assertEqual(bounded_process.run([sys.executable, "-c", "print('ok')"], timeout=2).stdout, "ok\n")
        self.assertEqual(bounded_process.run([sys.executable, "-c", "raise SystemExit(3)"], timeout=2).returncode, 3)
        with self.assertRaises(ValueError):
            bounded_process.run([sys.executable, "-c", "print('x'*1000)"], timeout=2, stdout_limit=10)
        with self.assertRaises(subprocess.TimeoutExpired):
            bounded_process.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)
        with self.assertRaises(ValueError):
            bounded_process.run([sys.executable], timeout=0)

    def test_container_cleanup_runs_after_timeout_and_failure_is_reported(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1] == "run":
                raise subprocess.TimeoutExpired("runtime", 1)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(bounded_process, "run", side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                bounded_process.run_container("runtime", "image@sha256:x", [], env={"GITHUB_AUTH_TOKEN": "secret"}, timeout=1)
        self.assertEqual(calls[0][4], calls[1][-1])
        self.assertNotIn("secret", calls[0])
        with patch.object(bounded_process, "run", return_value=subprocess.CompletedProcess([], 1, "", "permission denied")):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                bounded_process.run_container("runtime", "image", [], env={}, timeout=1)

    def test_snapshot_detects_dirty_content_and_tracks_untracked_and_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "file").write_text("one")
            subprocess.run(["git", "-C", str(root), "add", "file"], check=True)
            initial = snapshot.snapshot(root)
            (root / "file").write_text("two")
            self.assertNotEqual(initial, snapshot.snapshot(root))
            (root / "new").write_text("new")
            (root / "link").symlink_to("file")
            result = snapshot.snapshot(root)
            self.assertIn("new", result["files"])
            self.assertEqual(result["files"]["link"]["type"], "symlink")
            (root / "file").unlink()
            self.assertEqual(snapshot.snapshot(root)["files"]["file"]["type"], "missing")

    def test_scorecard_cli_blocks_unapproved_repository_output_before_execution(self):
        argv = ["helper", "--repo", "a/b", "--consent-file", "/consent",
                "--output", str(SCRIPTS.parents[2] / "unapproved.json")]
        with patch.object(sys, "argv", argv), patch.object(scorecard, "execute") as execute:
            self.assertEqual(scorecard.main(), 2)
        execute.assert_not_called()

    def test_local_provenance_is_not_the_container_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(scorecard, "discover_token", return_value=(None, None)), patch.object(scorecard.shutil, "which", return_value=sys.executable), patch.object(scorecard, "run_json", return_value=(True, "", False)):
                result = scorecard.execute("a/b", Path(temp) / "score.json", 5, None)
            self.assertIn("sha256", result["provenance"])
            self.assertNotIn("image", result["provenance"])

    def test_snapshot_cli_compares_content_and_refuses_target_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            baseline = Path(temp) / "baseline.json"
            with patch.object(sys, "argv", ["helper", "snapshot", "--repository", str(root), "--output", str(baseline)]):
                self.assertEqual(snapshot.main(), 0)
            argv = ["helper", "compare", "--repository", str(root), "--baseline", str(baseline)]
            with patch.object(sys, "argv", argv):
                self.assertEqual(snapshot.main(), 0)
            (root / "changed").write_text("new content")
            with patch.object(sys, "argv", argv):
                self.assertEqual(snapshot.main(), 2)
            with patch.object(sys, "argv", ["helper", "snapshot", "--repository", str(root), "--output", str(root / "forbidden.json")]):
                self.assertEqual(snapshot.main(), 2)

    def test_apply_cli_requires_exact_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            source = Path(temp) / "source.md"
            source.write_text("approved policy\n")
            record = Path(temp) / "approval.json"
            record.write_text(json.dumps({"scope": "apply", "repository": str(root), "allowed_paths": ["SECURITY.md"]}))
            argv = ["helper", "apply-file", "--repository", str(root), "--source", str(source), "--destination", "SECURITY.md", "--approval", str(record)]
            with patch.object(sys, "argv", argv):
                self.assertEqual(analyze.main(), 0)
            self.assertEqual((root / "SECURITY.md").read_text(), source.read_text())


if __name__ == "__main__":
    unittest.main()
