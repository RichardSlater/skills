#!/usr/bin/env python3
"""Plan a tmux pane split without mutating the tmux server."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from typing import TextIO

OWNER = "tmux-workflows"
CONTROL_ROLES = frozenset({"development", "utility"})


@dataclass(frozen=True)
class Pane:
    """Geometry and workflow metadata for one pane."""

    pane_id: str
    left: int
    top: int
    width: int
    height: int
    window_width: int
    window_height: int
    owner: str = ""
    role: str = ""

    @classmethod
    def from_tsv(cls, line: str) -> Pane:
        fields = line.rstrip("\n").split("\t")
        if len(fields) != 9:
            raise ValueError(f"expected 9 tab-separated fields, got {len(fields)}")
        pane_id, left, top, width, height, window_width, window_height, owner, role = (
            fields
        )
        if re.fullmatch(r"%[0-9]+", pane_id) is None:
            raise ValueError(f"invalid pane ID: {pane_id!r}")
        numeric = [int(value) for value in fields[1:7]]
        if any(value < 0 for value in numeric[:2]) or any(
            value <= 0 for value in numeric[2:]
        ):
            raise ValueError("pane positions must be non-negative and sizes positive")
        return cls(pane_id, *numeric, owner, role)


@dataclass(frozen=True)
class Profile:
    """Minimum usable geometry and preferred new-pane sizes."""

    pi_min_width: int
    pi_min_height: int
    pane_min_width: int
    pane_min_height: int
    side_size: int
    bottom_size: int
    reuse_controls: bool


PROFILES = {
    "utility": Profile(90, 18, 24, 6, 30, 8, True),
    "development": Profile(100, 18, 40, 6, 40, 7, True),
    "interactive": Profile(100, 20, 50, 12, 50, 12, False),
}


@dataclass(frozen=True)
class Plan:
    """A read-only recommendation for one explicit tmux split."""

    status: str
    purpose: str
    reason: str
    target_pane: str | None = None
    direction: str | None = None
    size: int | None = None
    source: str | None = None


def parse_panes(stream: TextIO) -> list[Pane]:
    """Parse the documented list-panes TSV format."""

    panes = []
    for line_number, line in enumerate(stream, start=1):
        if not line.strip():
            continue
        try:
            panes.append(Pane.from_tsv(line))
        except (TypeError, ValueError) as error:
            raise ValueError(f"line {line_number}: {error}") from error
    if not panes:
        raise ValueError("no panes supplied")
    return panes


def _split_candidate(
    pane: Pane,
    profile: Profile,
    approved_panes: frozenset[str],
) -> list[tuple[int, str, int, Pane]]:
    owned_control = pane.owner == OWNER and pane.role in CONTROL_ROLES
    if not (owned_control or pane.pane_id in approved_panes):
        return []

    candidates = []
    if (
        pane.left + pane.width == pane.window_width
        and pane.width >= profile.pane_min_width
    ):
        size = (pane.height - 1) // 2
        remainder = pane.height - size - 1
        if min(size, remainder) >= profile.pane_min_height:
            score = min(size, remainder) * pane.width
            candidates.append((score, "vertical", size, pane))

    if (
        pane.top + pane.height == pane.window_height
        and pane.height >= profile.pane_min_height
    ):
        size = (pane.width - 1) // 2
        remainder = pane.width - size - 1
        if min(size, remainder) >= profile.pane_min_width:
            score = min(size, remainder) * pane.height
            candidates.append((score, "horizontal", size, pane))

    return candidates


def _profile_with_overrides(profile: Profile, args: argparse.Namespace) -> Profile:
    values = {
        name: value
        for name, value in (
            ("pi_min_width", args.pi_min_width),
            ("pi_min_height", args.pi_min_height),
            ("pane_min_width", args.pane_min_width),
            ("pane_min_height", args.pane_min_height),
        )
        if value is not None
    }
    return replace(profile, **values)


def plan_layout(
    panes: list[Pane],
    pi_pane_id: str,
    purpose: str,
    *,
    approved_panes: frozenset[str] = frozenset(),
    profile: Profile | None = None,
) -> Plan:
    """Choose a deterministic split while preserving purpose-specific minimums."""

    if purpose not in PROFILES:
        raise ValueError(f"unknown purpose: {purpose}")
    selected_profile = profile or PROFILES[purpose]
    pane_by_id = {pane.pane_id: pane for pane in panes}
    if len(pane_by_id) != len(panes):
        raise ValueError("duplicate pane IDs supplied")
    try:
        pi_pane = pane_by_id[pi_pane_id]
    except KeyError as error:
        raise ValueError(f"Pi pane {pi_pane_id!r} was not supplied") from error

    window_sizes = {(pane.window_width, pane.window_height) for pane in panes}
    if len(window_sizes) != 1:
        raise ValueError("all panes must belong to the same tmux window")

    if selected_profile.reuse_controls:
        candidates = []
        for pane in panes:
            if pane.pane_id != pi_pane_id:
                candidates.extend(
                    _split_candidate(pane, selected_profile, approved_panes)
                )
        if candidates:
            _, direction, size, target = max(
                candidates,
                key=lambda candidate: (candidate[0], candidate[3].pane_id),
            )
            return Plan(
                "split",
                purpose,
                "extend the largest eligible control area without resizing Pi",
                target.pane_id,
                direction,
                size,
                "control",
            )

    max_side = pi_pane.width - selected_profile.pi_min_width - 1
    preferred_side = max(
        selected_profile.side_size,
        selected_profile.pane_min_width,
    )
    side_size = min(preferred_side, max_side)
    if (
        side_size >= selected_profile.pane_min_width
        and pi_pane.height >= selected_profile.pi_min_height
        and pi_pane.height >= selected_profile.pane_min_height
    ):
        return Plan(
            "split",
            purpose,
            "create a right-side pane and account for the one-cell divider",
            pi_pane_id,
            "horizontal",
            side_size,
            "pi",
        )

    max_bottom = pi_pane.height - selected_profile.pi_min_height - 1
    preferred_bottom = max(
        selected_profile.bottom_size,
        selected_profile.pane_min_height,
    )
    bottom_size = min(preferred_bottom, max_bottom)
    if (
        bottom_size >= selected_profile.pane_min_height
        and pi_pane.width >= selected_profile.pi_min_width
        and pi_pane.width >= selected_profile.pane_min_width
    ):
        return Plan(
            "split",
            purpose,
            "create a bottom pane and account for the one-cell divider",
            pi_pane_id,
            "vertical",
            bottom_size,
            "pi",
        )

    required_side_width = (
        selected_profile.pi_min_width + selected_profile.pane_min_width + 1
    )
    required_bottom_height = (
        selected_profile.pi_min_height + selected_profile.pane_min_height + 1
    )
    return Plan(
        "refuse",
        purpose,
        (
            "no eligible control pane can be extended and Pi is too small; "
            f"need at least {required_side_width} columns for a side split or "
            f"{required_bottom_height} rows for a bottom split"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", choices=sorted(PROFILES), required=True)
    parser.add_argument("--pi-pane", required=True)
    parser.add_argument("--approved-pane", action="append", default=[])
    parser.add_argument("--pi-min-width", type=int)
    parser.add_argument("--pi-min-height", type=int)
    parser.add_argument("--pane-min-width", type=int)
    parser.add_argument("--pane-min-height", type=int)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        panes = parse_panes(sys.stdin)
        profile = _profile_with_overrides(PROFILES[args.purpose], args)
        if min(
            profile.pi_min_width,
            profile.pi_min_height,
            profile.pane_min_width,
            profile.pane_min_height,
        ) <= 0:
            raise ValueError("minimum dimensions must be positive")
        plan = plan_layout(
            panes,
            args.pi_pane,
            args.purpose,
            approved_panes=frozenset(args.approved_pane),
            profile=profile,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(asdict(plan), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
