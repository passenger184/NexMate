"""Path safety for the Phase 2 code tools.

Every file operation the assistant performs must land inside the one
configured project root (SECURITY.md "Project-root scoping"). This module
is THE enforcement point: resolve first (symlinks, '..'), then verify —
never sanitize, never "helpfully" redirect. Anything that escapes the root
raises PathOutsideRootError with a message that says exactly why.
"""

from pathlib import Path

import config


class PathOutsideRootError(Exception):
    """A requested path resolves outside the project root. Rejected."""


def resolve_in_project(raw_path: str, root: Path | None = None) -> Path:
    """Resolve raw_path and guarantee it stays inside the project root.

    Accepts relative paths (resolved against the root) and absolute paths
    (accepted only if they are already inside it). Symlinks are resolved
    via Path.resolve() BEFORE containment is checked, so:

      - a symlink inside the root pointing elsewhere INSIDE it  -> allowed
      - a symlink inside the root pointing OUTSIDE it           -> rejected
      - any '../' chain or absolute path escaping the root      -> rejected

    Raises PathOutsideRootError for every escape. The error names both the
    original request and where it actually resolved to — loud, not silent.
    """
    if root is None:
        root = config.PROJECT_ROOT
    root = Path(root).resolve()

    if not raw_path or not raw_path.strip():
        raise PathOutsideRootError("Empty path requested")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    # resolve() follows symlinks and collapses '..' — containment is judged
    # on the REAL destination, never on the string the caller supplied.
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathOutsideRootError(
            f"Cannot resolve path {raw_path!r}: {exc}"
        ) from exc

    if resolved != root and root not in resolved.parents:
        raise PathOutsideRootError(
            f"Rejected: {raw_path!r} resolves to {resolved}, which is "
            f"outside the project root {root}. No redirection attempted."
        )
    return resolved
