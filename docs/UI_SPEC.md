# docs/UI_SPEC.md — Sidebar UI Design

Standing interaction/structure reference for the NexMate sidebar, not a
current-phase task list or an implementation-verification report. Phase 1
introduced the sidebar and Phase 2 introduced code-edit approval.
`docs/UI_VISUAL_SPEC_updated.md` is the canonical blue visual reference;
it supersedes the historical amber `docs/UI_VISUAL_SPEC.md` and conflicting
visual details here. `ARCHITECTURE.md` alone owns the current/target HLD.

The current bundle uses a floating toggle, direct FastAPI calls and
complete JSON responses. Real Bench/Desk installation remains unverified.
Navbar integration, authenticated Frappe-owned history, transcript
restoration, streaming/realtime and authorized page context are target
work, not delivered by this reference. See `progress/CURRENT.md` for
observed evidence and `EVALUATION.md` for future acceptance gates.

## Principle: native to ERPNext, not bolted on

Use Frappe Desk's own CSS custom properties and component conventions —
not a custom design system, not colors/fonts that clash with the rest of
Desk. If Frappe Desk has theme tokens for surfaces/text/borders, use them;
don't hardcode hex values. The goal is that someone opening this sidebar
shouldn't be able to tell it wasn't built by the Frappe team.

## Layout

- A slide-out panel from the right edge of the screen, toggled by an icon
  in the Desk navbar — not a permanently docked panel that eats screen
  space when unused.
- Resizable width, reasonable default (~380–420px).
- Header: app name/icon, a "start fresh" action (resets the visible
  thread, doesn't necessarily delete server-side history — see Memory
  spec), a close action.
- Scrollable message area, fixed input bar pinned to the bottom.

## Message rendering

- User messages: right-aligned, distinct background (accent tint).
- Assistant messages: left-aligned, no bubble — just text, so longer
  technical answers don't feel cramped inside a chat-bubble shape.
- Markdown rendering including fenced code blocks with syntax highlighting
  and a copy button.
- Citations render as small pills below the relevant answer (e.g. `[1]
  custom_app/validations.py`), not inline footnote markers cluttering the
  prose. Tapping a pill can show the section/snippet or link to the source.
- Confidence: visually distinguish `high`, `low` and `no_match` using the
  quiet inline treatment in `docs/UI_VISUAL_SPEC_updated.md`, not the
  earlier large-callout direction. Low/no-match must still clearly warn
  the user not to rely on an unsupported answer.

## Diff / edit approval (Phase 2 dependency)

When the live code agent proposes an edit:
- Render the diff inline in the conversation (added/removed lines colored
  distinctly), not in a separate modal — keeps question → explanation →
  proposed fix → decision as one readable thread.
- Two clear actions: reject, and approve-and-commit. No silent auto-apply,
  ever — this must always require an explicit tap, matching the git-gated
  workflow in `docs/PHASE_2_SPEC.md` and `SECURITY.md`.
- After approval, show a brief confirmation (e.g. "committed as
  `a1b2c3d`") so the user has an immediate reference back to git history.

## Conversation model

- One continuous thread per user by default — not a list of named,
  separately managed conversations. Matches how developers actually use
  tools like this day to day.
- "Start fresh" clears the visible thread. Whether it also clears
  server-side history depends on the Memory design — see
  `docs/PHASE_4_SPEC.md`.

## States to design for

- Loading/thinking (a lightweight typing-style indicator, not a full-panel
  spinner)
- Streaming response (text appearing incrementally, if the generation
  provider supports streaming — check `litellm`'s support per provider)
- Low-confidence / no-match (visually distinct, see above)
- Service unreachable (a clear, non-alarming error state — "can't reach
  the assistant right now" rather than a raw stack trace)
- Empty state on first open (a short prompt suggestion or two, not a blank
  box)

## Interaction basics

- Enter to send, Shift+Enter for a newline in the input.
- Focus the input automatically when the panel opens.
- Keyboard-accessible: the panel should be usable without a mouse for
  basic send/read flows.
