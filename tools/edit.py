"""Tier-2 edit flow: propose-as-diff, explicit confirm, apply + commit.

Implements docs/PHASE_2_SPEC.md's gated sequence exactly, with every
SECURITY.md guardrail enforced in code:

  1. git tree must be CLEAN before anything is proposed (refuse with
     guidance; never auto-stash).
  2. The proposal is a real unified diff — never just a description.
  3. apply_edit refuses unless confirmed=True is explicitly passed.
  4. Apply + `git add <one file>` + `git commit` = one atomic commit per
     edit. Batching is structurally impossible: a proposal touches exactly
     one file and dies on use.
  5. Refusals are loud and actionable: outside PROJECT_ROOT, untracked,
     git-ignored, ambiguous match, file changed since proposal.

Proposals live in an in-memory store with a TTL — they are ephemeral by
design; a restart discards them and the user re-proposes against fresh
state. find/replace semantics: `find` must occur EXACTLY once in the file
(ambiguity is refused with the observed count), `replace` may be empty
(deletion is legitimate).
"""

import difflib
import subprocess
import time
import uuid
from typing import Any

import config
from tools.pathsafe import PathOutsideRootError, resolve_in_project


class EditRefusal(Exception):
    """An edit was refused. `category` drives the HTTP mapping."""

    def __init__(self, category: str, detail: str):
        super().__init__(detail)
        self.category = category
        self.detail = detail


def _git(*args: str) -> str:
    """Run one git command in the project root; loud on failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=config.PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditRefusal("git_error", f"git could not run: {exc}") from exc
    if proc.returncode != 0:
        raise EditRefusal(
            "git_error",
            f"git {' '.join(args[:2])} failed ({proc.returncode}): "
            f"{proc.stderr.strip()}",
        )
    return proc.stdout


def _git_status() -> str:
    return _git("status", "--porcelain")


def _refuse_if_dirty(rel_path: str | None = None) -> None:
    """Clean-tree gate; names the target when IT is the dirt.

    An untracked target file IS tree dirt ('??' in porcelain), but
    "commit or stash" is a useless answer to "edit this untracked file" —
    the guardrail text says to say what's actually wrong instead.
    """
    status = _git_status()
    if not status.strip():
        return
    if rel_path:
        hits = [ln for ln in status.splitlines()
                if ln.endswith(" " + rel_path)]
        if any(ln.startswith("??") for ln in hits):
            raise EditRefusal(
                "untracked_file",
                f"{rel_path!r} exists but is NOT in version control. "
                "This tool only edits tracked files so every change "
                "stays revertible — `git add` it and commit first, or "
                "tell me how you'd like to proceed.",
            )
    raise EditRefusal(
        "dirty_tree",
        "Git tree is not clean — refusing to propose or apply any "
        "edit. Commit or stash first (do not ask me to auto-stash):\n"
        + "\n".join(status.splitlines()[:10]),
    )


def _git_check_ignore(rel: str) -> bool:
    """git check-ignore exit codes: 0 ignored, 1 not ignored."""
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=config.PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EditRefusal("git_error",
                          f"git check-ignore could not run: {exc}") from exc
    return proc.returncode == 0


# --- proposal store -----------------------------------------------------------

_PROPOSALS: dict[str, dict[str, Any]] = {}


def _prune_store() -> None:
    ttl = config.EDIT_PROPOSAL_TTL_MINUTES * 60
    now = time.time()
    expired = [k for k, v in _PROPOSALS.items() if now - v["created_at"] > ttl]
    for key in expired:
        del _PROPOSALS[key]
    while len(_PROPOSALS) > 50:  # hard cap; oldest first
        oldest = min(_PROPOSALS, key=lambda k: _PROPOSALS[k]["created_at"])
        del _PROPOSALS[oldest]


# --- public flow ---------------------------------------------------------------

def propose_edit(path: str, find: str, replace: str, message: str,
                 context: str = "") -> dict[str, Any]:
    """Validate an edit request fully; return it as a unified diff.

    `context` (optional) records the question/explanation that motivated
    the edit — it travels with the proposal and is indexed as a
    resolved_issue chunk on apply (Phase 4 project memory).

    NOTHING is written to disk here. Every refusal condition from
    SECURITY.md is checked up front so the user sees problems BEFORE they
    look at a diff, not after.
    """
    if not message or len(message.strip()) < 10:
        raise EditRefusal(
            "bad_message",
            "A commit message of at least 10 characters describing WHAT "
            "changed and WHY is required.",
        )
    if not find:
        raise EditRefusal("bad_request", "`find` must be non-empty.")
    if find == replace:
        raise EditRefusal("no_op", "`find` and `replace` are identical.")

    # Path safety first (read-only), so refusals can name the real target.
    try:
        safe = resolve_in_project(path)
    except PathOutsideRootError as exc:
        raise EditRefusal("outside_root", str(exc)) from exc
    if not safe.exists():
        raise EditRefusal("not_found",
                          f"No such file inside the project: {path!r}. "
                          "Creating new files via this tool is not "
                          "supported — untracked files can't be edited "
                          "safely under these guardrails.")
    if not safe.is_file():
        raise EditRefusal("bad_request",
                          f"{path!r} resolves to a non-file path.")
    rel = safe.relative_to(config.PROJECT_ROOT).as_posix()

    # Gate order mirrors the spec: clean tree before anything else. The
    # target file gets named when it is itself the dirt.
    _refuse_if_dirty(rel)
    if _git("ls-files", "--", rel).strip() == "":
        if _git_check_ignore(rel):
            raise EditRefusal(
                "ignored_file",
                f"{rel!r} is git-ignored (build artifacts, .env, caches…). "
                "Refusing per guardrails — tell me how you want to handle "
                "it (edit manually, force-add, etc.) and I won't touch it "
                "silently either way.",
            )
        raise EditRefusal(
            "untracked_file",
            f"{rel!r} exists but is NOT in version control. Edits must be "
            "revertible, so this tool only touches tracked files — commit "
            "it first (`git add {rel} && git commit`) or tell me how to "
            "proceed.".format(rel=rel),
        )

    try:
        original = safe.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EditRefusal("binary_file",
                          f"{rel!r} is not UTF-8 text.") from exc

    occurrences = original.count(find)
    if occurrences != 1:
        raise EditRefusal(
            "ambiguous_match",
            f"`find` occurs {occurrences} times in {rel!r} "
            f"({'zero' if occurrences == 0 else 'multiple'} — expected "
            "exactly 1). Include more surrounding context to make it "
            "unique.",
        )

    updated = original.replace(find, replace, 1)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    ))

    _prune_store()
    proposal_id = uuid.uuid4().hex[:12]
    _PROPOSALS[proposal_id] = {
        "created_at": time.time(),
        "rel_path": rel,
        "abs_path": str(safe),
        "original": original,
        "updated": updated,
        "message": message.strip(),
        "diff": diff,
        "context": (context or "").strip(),
    }
    return {
        "proposal_id": proposal_id,
        "path": rel,
        "diff": diff,
        "message": message.strip(),
        "expires_minutes": config.EDIT_PROPOSAL_TTL_MINUTES,
    }


def apply_edit(proposal_id: str, confirmed: bool) -> dict[str, Any]:
    """Apply a stored proposal after EXPLICIT confirmation; atomic commit.

    Re-validates the world at apply time — the tree may have changed since
    the proposal was made, which invalidates the diff the user saw.
    """
    if not confirmed:
        raise EditRefusal(
            "confirmation_required",
            "apply_edit requires confirmed=true — edits are never applied "
            "on implication.",
        )
    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise EditRefusal(
            "unknown_proposal",
            f"No live proposal {proposal_id!r} (expired, already applied, "
            "or service restarted). Propose again.",
        )
    age_min = (time.time() - proposal["created_at"]) / 60
    if age_min > config.EDIT_PROPOSAL_TTL_MINUTES:
        del _PROPOSALS[proposal_id]
        raise EditRefusal("expired_proposal",
                          f"Proposal {proposal_id!r} expired "
                          f"({age_min:.0f} min old).")

    # World may have moved since the user saw the diff. Most precise
    # diagnosis first: a changed target voids the approved diff even if
    # unrelated dirt exists; unrelated dirt alone still refuses.
    rel = proposal["rel_path"]
    if _git("ls-files", "--", rel).strip() == "":
        del _PROPOSALS[proposal_id]
        raise EditRefusal("untracked_file",
                          f"{rel!r} is no longer tracked; proposal voided.")
    if _current_content(rel) != proposal["original"]:
        del _PROPOSALS[proposal_id]
        raise EditRefusal(
            "stale_proposal",
            f"{rel!r} changed since the proposal was made — the diff the "
            "user approved no longer matches reality. Proposal discarded; "
            "propose again against current content.",
        )
    _refuse_if_dirty()

    # Write + stage + commit: one file, one commit, nothing batched.
    from pathlib import Path as _Path
    _Path(proposal["abs_path"]).write_text(proposal["updated"],
                                           encoding="utf-8")
    _git("add", "--", rel)
    _git("commit", "-m", proposal["message"], "--", rel)
    commit_hash = _git("rev-parse", "--short", "HEAD").strip()
    del _PROPOSALS[proposal_id]  # one-shot by design

    result = {
        "applied": True,
        "path": rel,
        "commit_hash": commit_hash,
        "message": proposal["message"],
        "diff": proposal["diff"],
    }

    # Phase 4 project memory: the confirmed edit becomes a retrievable
    # resolved_issue chunk. The edit itself is already committed and safe;
    # a memory failure must not undo it, but it must be VISIBLE.
    try:
        from tools import memory as memory_tool
        memory = memory_tool.index_resolution(
            rel_path=rel,
            commit_hash=commit_hash,
            message=proposal["message"],
            context=proposal.get("context", ""),
            diff=proposal["diff"],
        )
        result["memory"] = memory
    except Exception as exc:
        result["memory"] = {"indexed": False, "error": str(exc)}
    return result


def _current_content(rel: str) -> str:
    """Current content of a project-relative file (post-resolution)."""
    safe = resolve_in_project(rel)
    return safe.read_text(encoding="utf-8")
