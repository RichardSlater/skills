"""Regression tests for the automated Conventional Commit release contract."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("fixtures.json")
GITVERSION = ROOT / "GitVersion.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
PR_WORKFLOW = ROOT / ".github" / "workflows" / "validate-conventional-commit.yml"
HEADER = re.compile(r"^(?P<type>[a-z][a-z0-9-]*)(?:\([^)\r\n]+\))?(?P<breaking>!)?: (?P<description>\S.+)$")
BREAKING_FOOTER = re.compile(r"(?m)^BREAKING CHANGE: .+")


def validate(message: str) -> bool:
    """Return whether a squash-merge title/body follows the repository contract."""
    header = message.splitlines()[0] if message else ""
    return bool(HEADER.fullmatch(header))


def classify(messages: list[str]) -> str | None:
    """Apply the documented major > minor > patch release precedence."""
    increments: set[str] = set()
    for message in messages:
        header = message.splitlines()[0] if message else ""
        match = HEADER.fullmatch(header)
        if not match:
            continue
        if match.group("breaking") or BREAKING_FOOTER.search(message):
            increments.add("major")
        elif match.group("type") == "feat":
            increments.add("minor")
        elif match.group("type") == "fix":
            increments.add("patch")
    return next((item for item in ("major", "minor", "patch") if item in increments), None)


class ReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))

    def test_fixtures_validate_and_classify(self) -> None:
        for fixture in self.fixtures:
            with self.subTest(fixture=fixture["name"]):
                self.assertEqual(validate(fixture["messages"][0]), fixture["valid"])
                self.assertEqual(classify(fixture["messages"]), fixture["increment"])

    def test_non_releasing_commits_remain_in_qualifying_range(self) -> None:
        fixture = next(item for item in self.fixtures if item["name"] == "non-releasing retained")
        self.assertEqual(fixture["messages"], fixture["included_messages"])
        self.assertEqual(classify(fixture["included_messages"]), "minor")

    def test_gitversion_and_validator_match_the_contract(self) -> None:
        config = GITVERSION.read_text(encoding="utf-8")
        workflow = PR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("major-version-bump-message", config)
        self.assertIn("minor-version-bump-message", config)
        self.assertIn("patch-version-bump-message", config)
        self.assertIn("BREAKING CHANGE", config)
        self.assertIn("CONVENTIONAL_COMMIT", workflow)
        self.assertIn("feat", workflow)
        self.assertIn("fix", workflow)
        pattern = next(line.strip() for line in workflow.splitlines() if line.strip().startswith("pattern="))
        result = subprocess.run(
            ["bash", "-c", f'{pattern}\n[[ "$CONVENTIONAL_COMMIT" =~ $pattern ]]'],
            check=False,
            env={"CONVENTIONAL_COMMIT": "feat(release): automate conventional releases"},
        )
        self.assertEqual(result.returncode, 0)

    def test_release_workflow_keeps_read_and_write_boundaries(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("actions/attest-build-provenance@43d14bc2b83dec42d39ecae14e916627a18bb661", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349", workflow)
        self.assertIn("vars.RELEASE_APP_ID", workflow)
        self.assertIn("secrets.RELEASE_APP_PRIVATE_KEY", workflow)
        self.assertIn("steps.release-app-token.outputs.token", workflow)
        self.assertNotIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("RELEASE_GPG_PRIVATE_KEY", workflow)
        self.assertIn("RELEASE_GPG_PASSPHRASE", workflow)
        self.assertIn("RELEASE_GPG_KEY_ID", workflow)
        self.assertIn("git tag -s", workflow)
        self.assertIn('archive_name="$(basename "$ARCHIVE")"', workflow)
        self.assertIn('sha256sum "$archive_name"', workflow)
        self.assertNotIn('sha256sum "$ARCHIVE" > "$checksum"', workflow)
        self.assertIn("git verify-tag", workflow)


if __name__ == "__main__":
    unittest.main()
