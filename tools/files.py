"""Tier-1 file reading for the Phase 2 code tools (always-on, no confirmation).

read_project_file is the read_file tool: project-root scoped via
tools.pathsafe, size-capped, strict UTF-8 — a binary or oversized read is
a loud, explained error, never a silent partial.
"""

from typing import Any

import config
from tools.pathsafe import resolve_in_project


class NotAFileError(Exception):
    """The path exists but is not a regular file (directory, device, ...)."""


class FileTooLargeError(Exception):
    """The file exceeds MAX_READ_FILE_BYTES; refuse instead of truncating."""


class BinaryFileError(Exception):
    """The file is not valid UTF-8 text; refuse rather than guess."""


def read_project_file(raw_path: str) -> dict[str, Any]:
    """Read one project file, safely scoped and size-checked.

    Returns {path, absolute_path, content, size_bytes, line_count} where
    `path` is relative to the project root (stable for citations) and
    `absolute_path` is the resolved real location. Raises (loudly, with
    reasons): PathOutsideRootError, FileNotFoundError, NotAFileError,
    FileTooLargeError, BinaryFileError.
    """
    safe = resolve_in_project(raw_path)
    if not safe.exists():
        raise FileNotFoundError(f"No such file inside the project: {raw_path!r}")
    if not safe.is_file():
        raise NotAFileError(
            f"{raw_path!r} resolves to {safe}, which is not a regular file"
        )

    size = safe.stat().st_size
    if size > config.MAX_READ_FILE_BYTES:
        raise FileTooLargeError(
            f"{raw_path!r} is {size} bytes; reads are capped at "
            f"{config.MAX_READ_FILE_BYTES} (MAX_READ_FILE_BYTES). Raise the "
            "cap deliberately if you really need this file."
        )

    try:
        content = safe.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BinaryFileError(
            f"{raw_path!r} does not decode as UTF-8 (likely binary); "
            "refusing to return mangled content"
        ) from exc

    rel = safe.relative_to(config.PROJECT_ROOT).as_posix()
    return {
        "path": rel,
        "absolute_path": str(safe),
        "content": content,
        "size_bytes": size,
        "line_count": content.count("\n") + (0 if content.endswith("\n") else 1),
    }
