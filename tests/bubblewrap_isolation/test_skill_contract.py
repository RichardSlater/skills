"""Contract checks for the approved trusted-workflow Bubblewrap guidance."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BubblewrapSkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = (ROOT / "skills/bubblewrap-isolation/SKILL.md").read_text()
        cls.launcher = (ROOT / "skills/bubblewrap-isolation/scripts/run-isolated.sh").read_text()

    def test_host_workflow_exceptions_are_explicit_and_trusted_only(self):
        self.assertIn("only `git commit` and `git push`", self.skill)
        self.assertIn("`pre-commit` outside the sandbox", self.skill)
        self.assertIn("trusted repositories", self.skill)
        self.assertIn("do not authorize arbitrary host-side executables", self.skill)
        self.assertIn("permit disabling signing or quality gates", self.skill)

    def test_suspicious_artifacts_require_a_separate_workflow(self):
        self.assertIn("Assessing potentially malicious repositories", self.skill)
        self.assertIn("host-side exceptions below are not suitable", self.skill)

    def test_missing_prerequisites_never_fall_back_to_host_execution(self):
        self.assertIn("Do not fall back", self.skill)
        self.assertIn("Never silently relax the sandbox", self.skill)

    def test_standard_launcher_has_no_extra_authority(self):
        self.assertIn('[[ $# -ge 2 && $1 == "--" ]] || usage', self.launcher)
        for option in ("--clearenv", "--unshare-all", "--new-session", "--cap-drop ALL"):
            self.assertIn(option, self.launcher)
        self.assertNotIn("--share-net", self.launcher)
        self.assertNotIn("PRE_COMMIT_HOME", self.launcher)

    def test_project_writes_and_resource_limitations_are_disclosed(self):
        self.assertIn("does **not** protect project files", self.skill)
        self.assertIn("guarantee resource limits", self.skill)


if __name__ == "__main__":
    unittest.main()
