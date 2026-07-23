"""Bounded documentation scanning regressions (WP-12)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location("scan",Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"/"scripts"/"analyze_best_practices.py")
analyze=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)
class ScanTests(unittest.TestCase):
 def test_oversized_and_symlink_files_are_skipped(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); (root/"big.md").write_bytes(b"x"*(analyze.MAX_SCAN_FILE_BYTES+1)); (root/"normal.md").write_text("https://bestpractices.dev/projects/1"); (root/"link.md").symlink_to(root/"normal.md")
   ids,_,meta=analyze.scan_project_ids([Path("big.md"),Path("link.md"),Path("normal.md")],root=root)
   self.assertEqual(ids,{1}); self.assertEqual(meta["skipped"]["oversized"],1); self.assertEqual(meta["skipped"]["symlink"],1)
 def test_deadline_exhaustion_is_incomplete(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); (root/"a.md").write_text("x")
   ticks=iter((0.0, analyze.MAX_SCAN_SECONDS + 1))
   _,_,meta=analyze.scan_project_ids([Path("a.md")],root=root,clock=lambda: next(ticks))
   self.assertTrue(meta["limits_hit"])
if __name__=="__main__": unittest.main()
