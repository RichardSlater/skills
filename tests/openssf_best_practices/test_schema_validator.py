"""Pinned BadgeApp schema regression tests (WP-04)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "validate_best_practices.py"
spec = importlib.util.spec_from_file_location("validate_schema", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class SchemaValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = validator.load_schema()

    def test_invented_field_is_rejected(self) -> None:
        self.assertIn("unknown BadgeApp criterion", " ".join(validator.validate({"invented_status": "Met"}, self.schema)))

    def test_valid_field_in_wrong_section_is_rejected(self) -> None:
        errors = validator.validate({"floss_license_status": "Met"}, self.schema, "gold")
        self.assertIn("does not belong to gold", " ".join(errors))

    def test_na_is_checked_against_schema(self) -> None:
        self.assertIn("N/A is not allowed", " ".join(validator.validate({"floss_license_status": "N/A"}, self.schema)))
        self.assertEqual([], validator.validate({"build_status": "N/A"}, self.schema))

    def test_missing_or_corrupt_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "schema.json"
            with self.assertRaises(ValueError):
                validator.load_schema(path)
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                validator.load_schema(path)

    def test_all_schema_fields_have_level_and_section(self) -> None:
        self.assertTrue(self.schema["fields"])
        self.assertTrue(all(field["section"] and field["levels"] for field in self.schema["fields"].values()))

    def test_representative_official_fields_validate(self) -> None:
        proposal = {"description_good_status": "Met", "floss_license_status": "Met", "build_status": "N/A"}
        self.assertEqual([], validator.validate(proposal, self.schema))


if __name__ == "__main__":
    unittest.main()
