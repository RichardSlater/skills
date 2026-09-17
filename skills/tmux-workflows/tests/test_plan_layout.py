from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
import uuid
from dataclasses import replace
from io import StringIO
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from plan_layout import OWNER, PROFILES, Pane, parse_panes, plan_layout  # noqa: E402

PANE_FORMAT = (
    "#{pane_id}\t#{pane_left}\t#{pane_top}\t#{pane_width}\t"
    "#{pane_height}\t#{window_width}\t#{window_height}\t"
    "#{@pi_workflow_owner}\t#{@pi_workflow_role}"
)
TMUX = shutil.which("tmux")
if TMUX is None and Path("/usr/local/bin/tmux").is_file():
    TMUX = "/usr/local/bin/tmux"


def pane(
    pane_id: str = "%0",
    *,
    left: int = 0,
    top: int = 0,
    width: int = 180,
    height: int = 44,
    window_width: int = 180,
    window_height: int = 44,
    owner: str = "",
    role: str = "",
) -> Pane:
    return Pane(
        pane_id,
        left,
        top,
        width,
        height,
        window_width,
        window_height,
        owner,
        role,
    )


class LayoutPlannerTests(unittest.TestCase):
    def test_utility_uses_small_side_pane(self) -> None:
        plan = plan_layout(
            [pane(width=120, window_width=120)],
            "%0",
            "utility",
        )

        self.assertEqual(plan.status, "split")
        self.assertEqual(plan.direction, "horizontal")
        self.assertEqual(plan.size, 29)
        self.assertEqual(120 - plan.size - 1, 90)

    def test_development_side_split_accounts_for_divider(self) -> None:
        plan = plan_layout(
            [pane(width=160, window_width=160)],
            "%0",
            "development",
        )

        self.assertEqual(plan.direction, "horizontal")
        self.assertEqual(plan.size, 40)
        self.assertEqual(160 - plan.size - 1, 119)

    def test_strict_legacy_minimum_refuses_160_by_25_window(self) -> None:
        profile = replace(
            PROFILES["development"],
            pi_min_width=120,
            pi_min_height=20,
        )
        plan = plan_layout(
            [pane(width=160, height=25, window_width=160, window_height=25)],
            "%0",
            "development",
            profile=profile,
        )

        self.assertEqual(plan.status, "refuse")
        self.assertIn("161 columns", plan.reason)
        self.assertIn("27 rows", plan.reason)

    def test_owned_side_control_is_extended_before_pi(self) -> None:
        panes = [
            pane(width=139),
            pane(
                "%1",
                left=140,
                width=40,
                owner=OWNER,
                role="development",
            ),
        ]
        plan = plan_layout(panes, "%0", "development")

        self.assertEqual(plan.target_pane, "%1")
        self.assertEqual(plan.direction, "vertical")
        self.assertEqual(plan.size, 21)
        self.assertEqual(plan.source, "control")

    def test_operator_approved_unowned_pane_can_be_extended(self) -> None:
        panes = [
            pane(width=139),
            pane("%7", left=140, width=40),
        ]
        plan = plan_layout(
            panes,
            "%0",
            "utility",
            approved_panes=frozenset({"%7"}),
        )

        self.assertEqual(plan.target_pane, "%7")
        self.assertEqual(plan.source, "control")

    def test_unowned_pane_is_not_reused_without_approval(self) -> None:
        panes = [
            pane(width=139),
            pane("%7", left=140, width=40),
        ]
        plan = plan_layout(panes, "%0", "utility")

        self.assertEqual(plan.target_pane, "%0")
        self.assertEqual(plan.source, "pi")

    def test_approved_pane_must_meet_both_dimension_minimums(self) -> None:
        panes = [
            pane(width=169),
            pane("%7", left=170, width=10),
        ]
        plan = plan_layout(
            panes,
            "%0",
            "utility",
            approved_panes=frozenset({"%7"}),
        )

        self.assertEqual(plan.target_pane, "%0")
        self.assertEqual(plan.source, "pi")

    def test_larger_override_also_increases_planned_side_size(self) -> None:
        profile = replace(PROFILES["utility"], pane_min_width=35)
        plan = plan_layout(
            [pane(width=140, window_width=140)],
            "%0",
            "utility",
            profile=profile,
        )

        self.assertEqual(plan.direction, "horizontal")
        self.assertEqual(plan.size, 35)

    def test_interactive_never_reuses_owned_control(self) -> None:
        panes = [
            pane(width=139),
            pane(
                "%1",
                left=140,
                width=40,
                owner=OWNER,
                role="development",
            ),
        ]
        plan = plan_layout(panes, "%0", "interactive")

        self.assertEqual(plan.target_pane, "%0")
        self.assertEqual(plan.direction, "vertical")
        self.assertEqual(plan.source, "pi")

    def test_all_single_pane_plans_preserve_profile_minimums(self) -> None:
        for purpose, profile in PROFILES.items():
            for width in range(60, 221):
                for height in range(10, 61):
                    with self.subTest(purpose=purpose, width=width, height=height):
                        plan = plan_layout(
                            [
                                pane(
                                    width=width,
                                    height=height,
                                    window_width=width,
                                    window_height=height,
                                )
                            ],
                            "%0",
                            purpose,
                        )
                        if plan.status == "refuse":
                            continue
                        if plan.direction == "horizontal":
                            pi_width = width - plan.size - 1
                            self.assertGreaterEqual(pi_width, profile.pi_min_width)
                            self.assertGreaterEqual(plan.size, profile.pane_min_width)
                            self.assertGreaterEqual(height, profile.pi_min_height)
                            self.assertGreaterEqual(height, profile.pane_min_height)
                        else:
                            pi_height = height - plan.size - 1
                            self.assertGreaterEqual(pi_height, profile.pi_min_height)
                            self.assertGreaterEqual(plan.size, profile.pane_min_height)
                            self.assertGreaterEqual(width, profile.pi_min_width)
                            self.assertGreaterEqual(width, profile.pane_min_width)

    def test_parse_rejects_malformed_geometry(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 9"):
            parse_panes(StringIO("%0\\t0\\t0\\t120\n"))

    def test_parse_rejects_non_numeric_pane_id(self) -> None:
        geometry = "%bad\t0\t0\t120\t40\t120\t40\t\t\n"
        with self.assertRaisesRegex(ValueError, "invalid pane ID"):
            parse_panes(StringIO(geometry))


@unittest.skipUnless(TMUX, "tmux is not installed")
class TmuxIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.socket = f"tmux-workflows-test-{uuid.uuid4().hex}"
        self.tmux("new-session", "-d", "-s", "test", "-x", "180", "-y", "44")
        self.pi_pane = self.tmux(
            "list-panes", "-t", "test", "-F", "#{pane_id}"
        ).strip()

    def tearDown(self) -> None:
        subprocess.run(
            [TMUX, "-L", self.socket, "kill-server"],
            check=False,
            capture_output=True,
            text=True,
        )

    def tmux(self, *args: str) -> str:
        result = subprocess.run(
            [TMUX, "-L", self.socket, *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def panes(self) -> list[Pane]:
        output = self.tmux("list-panes", "-t", "test", "-F", PANE_FORMAT)
        return parse_panes(StringIO(output))

    def apply(self, purpose: str) -> str:
        plan = plan_layout(self.panes(), self.pi_pane, purpose)
        self.assertEqual(plan.status, "split")
        flag = "-h" if plan.direction == "horizontal" else "-v"
        new_pane = self.tmux(
            "split-window",
            "-d",
            "-t",
            plan.target_pane,
            flag,
            "-l",
            str(plan.size),
            "-P",
            "-F",
            "#{pane_id}",
        ).strip()
        self.tmux(
            "set-option",
            "-p",
            "-t",
            new_pane,
            "@pi_workflow_owner",
            OWNER,
        )
        self.tmux(
            "set-option",
            "-p",
            "-t",
            new_pane,
            "@pi_workflow_role",
            purpose,
        )
        return new_pane

    def test_four_development_panes_reuse_one_side_area(self) -> None:
        for _ in range(4):
            self.apply("development")

        panes = self.panes()
        pi_pane = next(item for item in panes if item.pane_id == self.pi_pane)
        controls = [item for item in panes if item.role == "development"]

        self.assertEqual(pi_pane.width, 139)
        self.assertEqual(len(controls), 4)
        self.assertTrue(all(item.width == 40 for item in controls))
        self.assertTrue(all(item.height >= 6 for item in controls))
        self.assertTrue(all(item.owner == OWNER for item in controls))


if __name__ == "__main__":
    unittest.main()
