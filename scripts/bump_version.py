"""EntityGuard - Security layer for anonymizing patient data
Copyright (C) 2026  Christopher Abanilla
SPDX-License-Identifier: AGPL-3.0-or-later

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Bump the canonical app version in pyproject.toml. The root package.json
# is Tailwind build tooling only and keeps its own version - it is not
# synced. The FastAPI app reads its version string directly from here via
# main.py's hard-coded fallback, so pyproject.toml is the single source.
#
# Usage:
#     uv run python scripts/bump_version.py --current       # print current version
#     uv run python scripts/bump_version.py patch|minor|major
#     uv run python scripts/bump_version.py 1.2.3            # explicit version
#     uv run python scripts/bump_version.py minor --commit   # also git add+commit+tag
#
# With --commit the bump is committed as "chore: bump version to vX.Y.Z"
# and tagged vX.Y.Z. Pushing the tag triggers .github/workflows/release.yml,
# which creates the GitHub Release with the CHANGELOG section as notes.

import argparse
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/daemolition/guardrails"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def read_current_version() -> str:
    """Read the current app version from pyproject.toml.

    Returns:
        The current version string, e.g. "0.6.0".
    """
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def compute_new_version(current: str, target: str) -> str:
    """Compute the new version from a bump component or explicit value.

    Args:
        current: Current version string, e.g. "0.6.0".
        target: "major", "minor", "patch", or an explicit "X.Y.Z" string.

    Returns:
        The new version string.

    Raises:
        ValueError: If target is neither a known bump component nor a
            valid "X.Y.Z" version string.
    """
    if VERSION_RE.match(target):
        return target

    major, minor, patch = (int(part) for part in current.split("."))
    if target == "major":
        return f"{major + 1}.0.0"
    if target == "minor":
        return f"{major}.{minor + 1}.0"
    if target == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Invalid bump target: {target!r}")


def write_pyproject_version(new_version: str) -> None:
    """Replace the version line in pyproject.toml in place."""
    text = PYPROJECT.read_text(encoding="utf-8")
    updated = re.sub(
        r'^version = ".*"$',
        f'version = "{new_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(updated, encoding="utf-8")


def update_changelog(current: str, new_version: str) -> bool:
    """Move the "[Unreleased]" CHANGELOG section under a new version heading.

    Renames "## [Unreleased]" to "## [<new_version>] — <today>" and inserts a
    fresh, empty "## [Unreleased]" above it, then rewrites the compare links
    at the bottom of the file. No-op (returns False) if the "[Unreleased]"
    section has no actual changelog bullets yet — bumping the version isn't
    reason enough to create an empty release section.

    Args:
        current: The version being bumped from, e.g. "0.6.0".
        new_version: The version being bumped to, e.g. "0.7.0".

    Returns:
        True if the changelog was updated, False if there was nothing to move.
    """
    text = CHANGELOG.read_text(encoding="utf-8")

    match = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not match or "\n- " not in ("\n" + match.group(1)):
        return False

    today = date.today().isoformat()
    heading = f"## [Unreleased]\n\n## [{new_version}] — {today}\n"
    updated = text[: match.start()] + heading + match.group(1) + text[match.end() :]

    # Rewrite the compare links at the bottom: whatever the [Unreleased]
    # link pointed at before (no tags yet -> "/compare/HEAD", or
    # "vX.Y.Z...HEAD"), it now points at the new version's tag, and a link
    # for the freshly released version is appended.
    updated = re.sub(
        rf"^\[Unreleased\]: {re.escape(REPO_URL)}/compare/.*$",
        f"[Unreleased]: {REPO_URL}/compare/v{new_version}...HEAD\n"
        f"[{new_version}]: {REPO_URL}/compare/v{current}...v{new_version}",
        updated,
        count=1,
        flags=re.MULTILINE,
    )

    CHANGELOG.write_text(updated, encoding="utf-8")
    return True


def commit_and_tag(new_version: str, changelog_updated: bool) -> None:
    """Commit the version bump and create a git tag."""
    files = [str(PYPROJECT)]
    if changelog_updated:
        files.append(str(CHANGELOG))
    subprocess.run(["git", "add", *files], cwd=PROJECT_ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: bump version to v{new_version}"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(["git", "tag", f"v{new_version}"], cwd=PROJECT_ROOT, check=True)


def main() -> None:
    """Parse CLI arguments and bump the app version accordingly."""
    parser = argparse.ArgumentParser(
        description="Bump the app version in pyproject.toml (and move the "
        "CHANGELOG [Unreleased] section)."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help='"major", "minor", "patch", or an explicit "X.Y.Z" version',
    )
    parser.add_argument(
        "--current", action="store_true", help="print current version and exit"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="also git add+commit+tag the bumped files",
    )
    args = parser.parse_args()

    current = read_current_version()

    if args.current:
        print(current)
        return

    if not args.target:
        parser.error("target is required unless --current is given")

    new_version = compute_new_version(current, args.target)

    write_pyproject_version(new_version)
    changelog_updated = update_changelog(current, new_version)
    if not changelog_updated:
        print(
            "Warning: CHANGELOG.md's [Unreleased] section is empty — "
            "no version section created.",
            file=sys.stderr,
        )

    if args.commit:
        commit_and_tag(new_version, changelog_updated)

    print(f"{current} -> {new_version}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)