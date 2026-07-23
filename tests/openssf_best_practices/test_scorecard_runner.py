"""Pinned Scorecard runtime regressions (WP-11)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("scorecard", Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"/"scripts"/"scorecard_runner.py")
scorecard=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(scorecard)
class ScorecardTests(unittest.TestCase):
 def test_artifact_is_digest_pinned(self): self.assertIn("@sha256:", scorecard.SCORECARD_ARTIFACT["image"])
 def test_capture_is_bounded(self): self.assertTrue(scorecard._capture("x"*(scorecard.MAX_CAPTURE_BYTES+1)).endswith("[TRUNCATED]"))
 def test_failure_has_provenance(self):
  with patch.object(scorecard.shutil,"which",return_value=None), patch.object(scorecard,"working_runtime",return_value=[]), patch.object(scorecard,"discover_token",return_value=(None,None)):
   value=scorecard.execute("owner/repo",Path("/tmp/x.json"),1,None)
  self.assertEqual(value["status"],"failed"); self.assertIn("provenance",value); self.assertIn("timeout_state",value["provenance"])
 def test_deadline_expiry_is_timeout(self):
  with self.assertRaises(TimeoutError): scorecard.remaining(0, lambda: 1)
if __name__=="__main__": unittest.main()
