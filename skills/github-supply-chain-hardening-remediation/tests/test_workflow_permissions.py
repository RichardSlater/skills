import importlib.util
from pathlib import Path
import unittest

import yaml

MODULE = Path(__file__).parents[1] / "scripts" / "workflow_permissions.py"
spec = importlib.util.spec_from_file_location("workflow_permissions", MODULE)
workflow_permissions = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(workflow_permissions)

SCORECARD = "ossf/scorecard-action@0864cf19026789058feabb7e87baa5f140aac736 # v2.3.3"
SARIF = "github/codeql-action/upload-sarif@ddf5ce7296213f5548c91e2dd19df2d77d2b2d66 # v3"


def workflow(permissions="permissions: read-all\n", job_permissions=""):
    return f"""name: scorecard

{permissions}jobs:
  analysis:
{job_permissions}    runs-on: ubuntu-latest
    steps:
      - uses: {SCORECARD}
        with:
          publish_results: true
      - uses: {SARIF}
        with:
          sarif_file: results.sarif
  unrelated:
    permissions:
      issues: write
    runs-on: ubuntu-latest
    steps:
      - run: echo unchanged
"""


class WorkflowPermissionTests(unittest.TestCase):
    def test_read_all_becomes_complete_least_privilege_mappings(self):
        result = workflow_permissions.remediate_workflow(workflow())
        data = yaml.safe_load(result)
        self.assertEqual(data["permissions"], {"contents": "read"})
        self.assertEqual(data["jobs"]["analysis"]["permissions"], {
            "contents": "read", "security-events": "write", "id-token": "write",
        })
        self.assertEqual(data["jobs"]["unrelated"]["permissions"], {"issues": "write"})

    def test_existing_mappings_are_merged_not_overwritten(self):
        source = workflow(
            permissions="permissions:\n  actions: read\n",
            job_permissions="    permissions:\n      packages: read\n",
        )
        result = workflow_permissions.remediate_workflow(source)
        data = yaml.safe_load(result)
        self.assertEqual(data["permissions"], {"actions": "read", "contents": "read"})
        self.assertEqual(data["jobs"]["analysis"]["permissions"], {
            "packages": "read", "contents": "read", "security-events": "write", "id-token": "write",
        })
        self.assertIn("# v2.3.3", result)
        self.assertIn("# v3", result)

    def test_insufficient_existing_permissions_are_corrected_without_dropping_others(self):
        source = workflow(
            "permissions:\n  contents: none # baseline\n",
            "    permissions:\n      contents: none # needed for checkout\n      security-events: read\n      id-token: read\n      attestations: write\n",
        )
        data = yaml.safe_load(workflow_permissions.remediate_workflow(source))
        self.assertEqual(data["permissions"]["contents"], "read")
        self.assertEqual(data["jobs"]["analysis"]["permissions"]["contents"], "read")
        self.assertEqual(data["jobs"]["analysis"]["permissions"]["security-events"], "write")
        self.assertEqual(data["jobs"]["analysis"]["permissions"]["id-token"], "write")
        self.assertEqual(data["jobs"]["analysis"]["permissions"]["attestations"], "write")

    def test_validator_rejects_each_missing_permission(self):
        source = workflow("permissions:\n  contents: read\n", "    permissions:\n      contents: read\n")
        errors = workflow_permissions.validate_scorecard_workflow(source)
        self.assertIn("jobs.analysis requires security-events: write", errors)
        self.assertIn("jobs.analysis requires id-token: write", errors)

    def test_sarif_requires_security_events_and_scorecard_requires_contents(self):
        source = workflow("permissions:\n  contents: read\n", "    permissions:\n      id-token: write\n")
        errors = workflow_permissions.validate_scorecard_workflow(source)
        self.assertIn("jobs.analysis requires contents: read", errors)
        self.assertIn("jobs.analysis requires security-events: write", errors)

    def test_remediation_is_idempotent_and_yaml_is_valid(self):
        once = workflow_permissions.remediate_workflow(workflow())
        twice = workflow_permissions.remediate_workflow(once)
        self.assertEqual(once, twice)
        self.assertIsInstance(yaml.safe_load(twice), dict)
        self.assertEqual(workflow_permissions.validate_scorecard_workflow(twice), [])

    def test_template_has_full_sha_pins_and_valid_permissions(self):
        template = workflow_permissions.scorecard_workflow_template()
        self.assertNotIn("@v3", template)
        self.assertEqual(workflow_permissions.validate_scorecard_workflow(template), [])
        self.assertIsInstance(yaml.safe_load(template), dict)


if __name__ == "__main__":
    unittest.main()
