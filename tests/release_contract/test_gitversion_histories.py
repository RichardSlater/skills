"""Optional executable GitVersion history rehearsals.

Set GITVERSION_BIN to the dotnet-gitversion executable. CI exercises the same
configuration through the pinned action; this test makes local rehearsal
repeatable without committing a tool binary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
GITVERSION = os.environ.get("GITVERSION_BIN")


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


def version(repo: Path) -> str:
    result = run(GITVERSION, str(repo), "/output", "json", cwd=repo)
    payload = json.loads(result[result.index("{") :])
    return payload["MajorMinorPatch"]


@unittest.skipUnless(GITVERSION, "set GITVERSION_BIN to run GitVersion rehearsals")
class GitVersionHistoryTests(unittest.TestCase):
    def make_repo(self, messages: list[str], tag: str | None = None) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = Path(temp.name)
        run("git", "init", "-q", "-b", "main", cwd=repo)
        run("git", "config", "user.email", "test@example.com", cwd=repo)
        run("git", "config", "user.name", "Release fixture", cwd=repo)
        shutil.copy(ROOT / "GitVersion.yml", repo / "GitVersion.yml")
        for number, message in enumerate(messages):
            (repo / "fixture.txt").write_text(str(number), encoding="utf-8")
            run("git", "add", ".", cwd=repo)
            run("git", "commit", "-qm", message, cwd=repo)
            if tag and number == 0:
                run("git", "tag", "-a", tag, "-m", tag, cwd=repo)
        return repo

    def test_no_tag_existing_tag_mixed_and_non_releasing_histories(self) -> None:
        cases = (
            (["feat: initial feature"], None, "0.1.0"),
            (["chore: initial", "fix: correct behavior"], "v1.0.2", "1.0.3"),
            (["chore: initial", "fix: correct behavior", "feat: add capability", "feat!: remove API"], "v1.0.2", "2.0.0"),
            # GitVersion provides an informational patch candidate here; the release
            # workflow's Conventional Commit gate correctly makes this a no-op.
            (["chore: initial", "docs: clarify setup"], "v1.0.2", "1.0.3"),
        )
        for messages, tag, expected in cases:
            with self.subTest(messages=messages):
                self.assertEqual(version(self.make_repo(messages, tag)), expected)


if __name__ == "__main__":
    unittest.main()
