"""Validator semantic and evidence-safety regression tests (WP-08)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("validator_security", Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices" / "scripts" / "validate_best_practices.py")
validator = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(validator)

class ValidatorSecurityTests(unittest.TestCase):
    def setUp(self): self.schema = validator.load_schema()
    def errors(self, value): return validator.validate({"floss_license_status": "Met", "floss_license_justification": value}, self.schema)
    def test_question_and_unknown_are_unanswered(self):
        self.assertEqual([], validator.validate({"floss_license_status": "?"}, self.schema))
        self.assertEqual([], validator.validate({"floss_license_status": "unknown"}, self.schema))
    def test_wrong_type_is_a_normal_error(self):
        self.assertIn("expected one", " ".join(validator.validate({"floss_license_status": []}, self.schema)))
    def test_unsafe_evidence_is_rejected_without_echoing_value(self):
        for value in ("https://user:password@example.com/x", "http://example.com/x", "https://127.0.0.1/x", "C:\\secret.txt", "Authorization: Bearer very-secret-value", "-----BEGIN PRIVATE KEY-----"):
            errors = self.errors(value)
            self.assertTrue(errors)
            self.assertNotIn(value, " ".join(errors))
    def test_public_https_evidence_passes(self):
        self.assertEqual([], self.errors("https://github.com/owner/repository/blob/main/LICENSE"))
    def test_error_order_is_stable(self):
        data = {"zzz_status": "Met", "aaa_status": [], "floss_license_justification": 5}
        self.assertEqual(validator.validate(data, self.schema), validator.validate(data, self.schema))

if __name__ == "__main__": unittest.main()
