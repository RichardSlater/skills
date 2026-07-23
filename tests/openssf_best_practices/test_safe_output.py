"""Filesystem confinement regressions (WP-06)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "safe_output.py"
spec = importlib.util.spec_from_file_location("safe_output", SCRIPT)
safe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(safe)

class SafeOutputTests(unittest.TestCase):
    def test_rejects_symlink_parent_and_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"; outside = Path(temp) / "outside"
            root.mkdir(); outside.mkdir(); (root / "reports").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(safe.UnsafePathError): safe.atomic_write_text(root.resolve(), "reports/x.json", "x")
            (root / "reports").unlink(); (root / "reports").mkdir(); (root / "reports" / "x.json").symlink_to(outside / "x.json")
            with self.assertRaises(safe.UnsafePathError): safe.atomic_write_text(root.resolve(), "reports/x.json", "x")

    def test_rejects_absolute_traversal_and_sibling_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"; root.mkdir()
            for path in ("/tmp/x", "../outside/x", "C:\\outside\\x", "\\\\host\\share\\x"):
                with self.assertRaises(safe.UnsafePathError): safe.atomic_write_text(root.resolve(), path, "x")

    def test_regular_file_is_atomically_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); target = root / "reports" / "x.json"; target.parent.mkdir(); target.write_text("old")
            safe.atomic_write_text(root.resolve(), "reports/x.json", "new", allowed_subtrees=("reports",))
            self.assertEqual(target.read_text(), "new")

if __name__ == "__main__": unittest.main()
