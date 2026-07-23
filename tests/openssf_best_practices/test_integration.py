"""Offline workflow integration regressions (WP-14)."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"; SCRIPTS=ROOT/"scripts"; sys.path.insert(0,str(SCRIPTS))
import approval
spec=importlib.util.spec_from_file_location("integration_analyze",SCRIPTS/"analyze_best_practices.py")
analyze=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)
class IntegrationTests(unittest.TestCase):
 def test_public_read_only_discovery_fixture(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); (root/"README.md").write_text("https://bestpractices.dev/projects/7")
   ids,evidence,meta=analyze.scan_project_ids([Path("README.md")],root=root)
   self.assertEqual(ids,{7}); self.assertEqual(meta["files_scanned"],1); self.assertFalse((root/".bestpractices.dev").exists())
 def test_approved_apply_is_limited_to_approved_path(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); record_path=root/"approval.json"; record_path.write_text(json.dumps({"scope":"apply","repository":str(root),"allowed_paths":["SECURITY.md"]}))
   record=approval.load_approval(record_path,root); approval.require_approved_path(record,"SECURITY.md")
   with self.assertRaises(approval.ApprovalError): approval.require_approved_path(record,"README.md")
 def test_missing_evidence_creates_no_success_report(self):
  with tempfile.TemporaryDirectory() as temp:
   output=Path(temp)/"summary.json"
   result=subprocess.run([sys.executable,str(SCRIPTS/"analyze_best_practices.py"),"summarize","--project",str(Path(temp)/"missing.json"),"--output",str(output)],capture_output=True,text=True)
   self.assertEqual(result.returncode,2); self.assertFalse(output.exists())
class CompletenessTests(unittest.TestCase):
 def test_audit_findings_have_named_regressions(self):
  names="\n".join(path.read_text() for path in Path(__file__).resolve().parent.glob("test_*.py"))
  for finding in ("portability","project identity","schema","summary","safe_output","privacy","proposal"):
   self.assertIn(finding.replace(" ","_"),names.replace(" ","_"))
if __name__=="__main__": unittest.main()
