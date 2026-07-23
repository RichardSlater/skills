"""Documentation and official API regressions (WP-13)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"
spec=importlib.util.spec_from_file_location("doc_api",ROOT/"scripts"/"analyze_best_practices.py")
analyze=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)
class DocumentationApiTests(unittest.TestCase):
 def test_fetch_has_no_unsupported_accept_negotiation(self):
  class Response:
   def __enter__(self): return self
   def __exit__(self,*_): return False
   def read(self,*_): return b'{"id":1}'
  with patch.object(analyze,"urlopen",return_value=Response()) as request:
   analyze.fetch_project(1)
  self.assertNotIn("Accept",request.call_args.args[0].headers)
 def test_both_official_automation_paths_are_recognized(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); (root/".bestpractices.json").write_text("{}"); (root/".project.d").mkdir(); (root/".project.d/bestpractices.json").write_text("{}")
   self.assertTrue((root/".bestpractices.json").exists()); self.assertTrue((root/".project.d/bestpractices.json").exists())
 def test_local_markdown_links_resolve(self):
  text=(ROOT/"SKILL.md").read_text()
  for link in ("references/field-format.md","references/truthfulness.md","references/schema/PROVENANCE.md",".gitignore.example"):
   self.assertIn(link,text); self.assertTrue((ROOT/link).exists())
if __name__=="__main__": unittest.main()
