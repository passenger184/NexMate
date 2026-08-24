"""Tier-1 code search (grep-equivalent) over the project root.

File discovery uses `git ls-files --cached --others --exclude-standard`:
tracked plus untracked-but-not-ignored files — i.e. exactly the project's
real source, with git-ignored junk (caches, venvs, build output) excluded
for result quality. This is a QUALITY filter, not a security boundary:
every file is still re-scoped through tools.pathsafe before being read,
so nothing outside PROJECT_ROOT can ever be returned regardless of what
git reports.

The query is treated as a regex; if it doesn't compile, it silently
degrades to a literal search of the same string (and says so in the
response). Case-sensitive by default, grep-style.
"""

import re
import subprocess
from typing import Any

import config
from tools.pathsafe import PathOutsideRootError, resolve_in_project


class SearchError(Exception):
    """Search could not run (e.g. git unavailable). Loud, never degraded."""


def _list_project_files() -> list[str]:
    """Project files as git sees them: tracked + untracked-unignored."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=config.PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SearchError(f"git ls-files could not run: {exc}") from exc
    if proc.returncode != 0:
        raise SearchError(
            f"git ls-files failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _compile_query(query: str, ignore_case: bool) -> tuple[re.Pattern, bool]:
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.compile(query, flags), False
    except re.error:
        # Not a valid regex: search for the literal string instead of erroring.
        return re.compile(re.escape(query), flags), True


def search_project(
    query: str, ignore_case: bool = False
) -> dict[str, Any]:
    """Search project text files for a pattern.

    Returns {query, regex_source, literal_fallback, ignore_case, matches:
    [{path, line_number, line}], total_matches, truncated, files_searched,
    skipped_binary, skipped_large}. `matches` is capped at
    MAX_SEARCH_RESULTS; total_matches keeps counting past the cap so the
    caller knows what they're not seeing.
    """
    pattern, literal_fallback = _compile_query(query, ignore_case)

    matches: list[dict[str, Any]] = []
    total_matches = 0
    truncated = False
    files_searched = 0
    skipped_binary = 0
    skipped_large = 0

    for rel_path in _list_project_files():
        if total_matches >= config.SEARCH_HARD_MATCH_CAP:
            truncated = True
            break

        # Security boundary, applied per-file even though git listed it.
        try:
            safe = resolve_in_project(rel_path)
        except PathOutsideRootError:
            continue  # git reported it; scoping still refuses to read it

        if not safe.is_file():  # renames/deletions between listing and read
            continue
        if safe.stat().st_size > config.MAX_READ_FILE_BYTES:
            skipped_large += 1
            continue
        try:
            text = safe.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped_binary += 1
            continue
        files_searched += 1

        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            total_matches += 1
            if len(matches) < config.MAX_SEARCH_RESULTS:
                matches.append({
                    "path": rel_path,
                    "line_number": lineno,
                    "line": line.strip()[:config.MATCH_LINE_MAX_CHARS],
                })
            else:
                truncated = True

    return {
        "query": query,
        "regex_source": pattern.pattern,
        "literal_fallback": literal_fallback,
        "ignore_case": ignore_case,
        "matches": matches,
        "total_matches": total_matches,
        "truncated": truncated,
        "files_searched": files_searched,
        "skipped_binary": skipped_binary,
        "skipped_large": skipped_large,
    }
