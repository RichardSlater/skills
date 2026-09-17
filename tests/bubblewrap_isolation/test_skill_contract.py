"""Contract checks for the Bubblewrap isolation skill guidance."""

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPOSITORY_ROOT / "skills" / "bubblewrap-isolation" / "SKILL.md"
LAUNCHER_PATH = (
    REPOSITORY_ROOT
    / "skills"
    / "bubblewrap-isolation"
    / "scripts"
    / "run-isolated.sh"
)


class BubblewrapSkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.launcher = LAUNCHER_PATH.read_text(encoding="utf-8")

    def test_pre_commit_requires_an_isolated_executable_and_version_probe(self):
        self.assertIn("## Bootstrap-dependent quality gates", self.skill)
        self.assertIn(
            '"$RUN_ISOLATED" -- sh -c '
            "'command -v pre-commit && pre-commit --version'",
            self.skill,
        )
        self.assertIn("path and version", self.skill)

    def test_missing_or_skewed_sandbox_executable_stops_without_fallback(self):
        self.assertIn("cannot find `pre-commit`", self.skill)
        self.assertIn("unexpected installation or version", self.skill)
        self.assertIn("stop and report the discrepancy", self.skill)
        self.assertIn("Do not silently substitute a host-side command", self.skill)

    def test_offline_bootstrap_failures_stop_before_escalation(self):
        for dependency in (
            "hook repository",
            "hook executable",
            "language environment",
        ):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, self.skill)
        self.assertIn("expected offline-bootstrap failure", self.skill)
        self.assertIn(
            "Do not retry with networking, extra mounts, or unsandboxed execution",
            self.skill,
        )

    def test_cache_guidance_separates_read_only_content_and_ephemeral_state(self):
        self.assertIn("cache dedicated to the current project", self.skill)
        self.assertIn("persistent hook content read-only", self.skill)
        self.assertIn("writable runtime state to ephemeral storage", self.skill)
        self.assertIn("Never automatically mount the user's global pre-commit cache", self.skill)
        self.assertIn("cross-project cache poisoning", self.skill)

    def test_standard_launcher_interface_and_authority_remain_restricted(self):
        self.assertIn("Usage: %s -- command [argument ...]", self.launcher)
        self.assertIn('[[ $# -ge 2 && $1 == "--" ]] || usage', self.launcher)
        self.assertIn("--clearenv", self.launcher)
        self.assertIn("--unshare-all", self.launcher)
        self.assertNotIn("--share-net", self.launcher)
        self.assertNotIn("PRE_COMMIT_HOME", self.launcher)
        self.assertIn("standard launcher remains private-home and no-network", self.skill)


if __name__ == "__main__":
    unittest.main()
