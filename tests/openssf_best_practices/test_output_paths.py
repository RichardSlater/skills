"""Generated assessment output policy regressions (WP-10)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("analyze_output_paths", Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "analyze_best_practices.py")
analyze = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(analyze)

class OutputPathTests(unittest.TestCase):
    def test_unignored_repository_output_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); subprocess.run(["git", "init", "-q", str(root)], check=True)
            self.assertFalse(analyze.assessment_output_is_ignored(root, Path(".bestpractices.dev/discovery.json")))
            self.assertFalse((root / ".bestpractices.dev" / "discovery.json").exists())
    def test_ignored_evidence_directory_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(".bestpractices.dev/\n")
            self.assertTrue(analyze.assessment_output_is_ignored(root, Path(".bestpractices.dev/discovery.json")))
    def test_documentation_explains_example_activation(self):
        text = (Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "SKILL.md").read_text()
        self.assertIn("not active automatically", text)

if __name__ == "__main__": unittest.main()
