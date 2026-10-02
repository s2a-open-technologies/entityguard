"""
Static asset URL helper with cache busting.
Copyright (C) 2026  Christopher Abanilla

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

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "static"


def asset_url(relative_path: str) -> str:
    """
    Build a /static URL with the file's mtime as a cache-busting query.

    Browsers cache admin.js/admin.css aggressively; without a version
    marker a code change is not picked up until a hard refresh. Appending
    the mtime forces a reload exactly when the file changes.

    Args:
        relative_path: Path relative to the static dir, e.g. "js/admin.js".

    Returns:
        str: URL like "/static/js/admin.js?v=1727856000"; the plain path if
            the file cannot be stat'ed.
    """
    full_path = STATIC_DIR / relative_path
    try:
        version = int(full_path.stat().st_mtime)
    except OSError:
        return f"/static/{relative_path}"
    return f"/static/{relative_path}?v={version}"