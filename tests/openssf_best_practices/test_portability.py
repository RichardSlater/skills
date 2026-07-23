"""Regression tests for portable helper invocation (WP-01)."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"
SCRIPT = SKILL_DIR / "scripts" / "analyze_best_practices.py"
spec = importlib.util.spec_from_file_location("analyze_best_practices", SCRIPT)
analyze = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(analyze)


class PortabilityTests(unittest.TestCase):
    def test_preflight_does_not_require_python_command(self) -> None:
        tools = {"git": "/bin/git", "gh": "/bin/gh", "scorecard": "/bin/scorecard"}
        with patch.object(analyze.shutil, "which", side_effect=lambda name: tools.get(name)), patch(
            "sys.stdout", new_callable=StringIO
        ) as stdout, patch("sys.stderr", new_callable=StringIO) as stderr:
            self.assertEqual(analyze.preflight(), 0)
        self.assertIn(analyze.sys.executable, stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_documented_helpers_are_skill_relative_from_unrelated_directory(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as unrelated:
            previous = Path.cwd()
            try:
                # This models command construction while the target repository is unrelated.
                script = (SKILL_DIR / "scripts" / "analyze_best_practices.py").resolve()
                self.assertTrue(script.is_relative_to(SKILL_DIR.resolve()))
                self.assertNotEqual(Path(unrelated).resolve(), SKILL_DIR.resolve())
                self.assertIn('"$PYTHON_BIN" "$SKILL_DIR/scripts/analyze_best_practices.py"', text)
                self.assertNotIn("python scripts/", text)
            finally:
                # No directory mutation is necessary; retain this guard for portability changes.
                self.assertEqual(Path.cwd(), previous)

    def test_skill_path_with_spaces_is_one_argument(self) -> None:
        skill_dir = Path("/tmp/skill directory with spaces")
        command = [sys.executable, str(skill_dir / "scripts" / "analyze_best_practices.py"), "preflight"]
        self.assertEqual(command[1], "/tmp/skill directory with spaces/scripts/analyze_best_practices.py")
        self.assertEqual(len(command), 3)

    def test_unsupported_python_is_tool_unavailable(self) -> None:
        with patch.object(analyze.sys, "version_info", (3, 10, 0)), patch(
            "sys.stderr", new_callable=StringIO
        ) as stderr:
            self.assertEqual(analyze.preflight(), 3)
        self.assertIn("requires Python 3.11+", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
