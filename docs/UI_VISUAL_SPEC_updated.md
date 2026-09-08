# docs/UI_VISUAL_SPEC.md — Visual Design Spec (Reference-Matched)

**This supersedes any earlier visual direction.** The current build does
not match intent — flat panel, no citation pill styling, no diff-card
treatment, and two competing accent colors (a blue dropdown and an orange
button) that were never specified anywhere. This doc gives literal values,
not concepts to reinterpret. Match it exactly. If something here is
ambiguous, ask — don't improvise a variation.

## Non-negotiable: one accent color only

`#2E6FF2` (a clean mid-blue) is the ONLY accent color in the entire UI —
used for the user's own message bubble and the send action. Nothing else
gets a competing bright color. No orange, no second blue, no gradient. If
you find an orange, teal, or any other accent already in the CSS, remove
it and replace it with `#2E6FF2` or a neutral.

## Color tokens

| Token | Hex | Role |
|---|---|---|
| `--panel-bg` | `#15171C` | Whole panel background |
| `--surface-card` | `#1C1E25` | Diff card, code blocks — one shade lighter than panel bg |
| `--border` | `#2A2D36` | Hairline borders on cards, citation pills, input field |
| `--text-primary` | `#F2F3F5` | Body text, headings |
| `--text-muted` | `#9BA0AC` | Timestamps, placeholder text, citation label text |
| `--accent` | `#2E6FF2` | User message bubble, send arrow, focus rings — ONLY these |
| `--success` | `#3DBD73` | Confidence checkmark + "high confidence" text, diff added lines |
| `--danger` | `#E5484D` | Diff removed lines, low-confidence/error states |

## Component-by-component

**Header**: panel background, no visible border unless a 1px `--border`
line is needed for separation. Left: small circular icon + "ERPNext
copilot" in `--text-primary`, medium weight. Right: refresh icon and close
icon in `--text-muted`, no background/button chrome around them — icons
alone, hover state only.

**User message**: right-aligned bubble, `--accent` background, white text,
fully rounded corners (not a sharp rectangle), max-width ~80% of panel,
padding ~10px 14px.

**Assistant message**: NO bubble — plain `--text-primary` text directly on
`--panel-bg`, left-aligned, comfortable line-height (1.6). This is
intentional: a bubble around every long technical answer makes it feel
cramped.

**Citation pill**: small rounded-rectangle, `--surface-card` background,
1px `--border`, `--text-muted` text, small font size (~11px), format
`[1] path/to/file.py`. Sits directly below the assistant message it
supports, wraps to multiple pills if there are several sources.

**Confidence indicator**: small inline row directly below the citation
pills — a checkmark icon + "high confidence" in `--success`, OR (for low/
no-match) a warning-style icon + label in `--danger`. Text size ~11px.
Never a large banner; always this small, quiet, inline treatment.

**Diff / proposed-fix card** (Phase 2 edit approval): `--surface-card`
background, 1px `--border`, rounded corners (~8px), padding ~12px.
- Header row inside the card: `Proposed fix — <filename>` in
  `--text-muted`, small.
- Below it, a monospace code block: removed lines get a `--danger`-tinted
  background (roughly 12% opacity) with a `-` prefix in `--danger`; added
  lines get a `--success`-tinted background (12% opacity) with a `+`
  prefix in `--success`. Use an actual monospace font (`JetBrains Mono`,
  `IBM Plex Mono`, or system monospace fallback) — not the UI's regular
  font.
- Two buttons below the code block, equal width, side by side, ~8px gap:
  - **Reject**: outlined/ghost style — 1px `--border`, transparent
    background, `--text-primary` text. No fill.
  - **Approve and commit**: solid fill — light/white background
    (`#F2F3F5`), dark text (`#15171C`) for maximum contrast as the clear
    primary action. This is the one high-contrast element in the card;
    everything else stays low-contrast/quiet by comparison.

**Input bar**: pinned to the bottom of the panel, `--panel-bg` background,
1px `--border` separating it from the message area above. A single
rounded input field (`--surface-card` fill, `--border` outline, placeholder
in `--text-muted`) taking most of the width, with a small send arrow icon
in `--accent` at the right edge — icon only, not a filled button (this
avoids introducing a second button style competing with the diff card's
Approve button).

**Quick-question suggestion chips** (shown on empty/first open): same
pill treatment as citations — `--surface-card` fill, 1px `--border`,
`--text-primary` text, rounded corners, stacked or wrapped, not styled as
bright/filled buttons.

**Mode dropdown** (developer/employee): plain — `--surface-card` fill,
`--border` outline, `--text-primary` text, small chevron icon. NOT filled
with `--accent` or any other bright color — it's a neutral control, not a
call to action.

## What to remove from the current build

- The orange "Send" button — replace with the icon-only accent-colored
  arrow described above.
- Whatever gave the mode dropdown its current blue fill — make it neutral
  per the spec above.
- Any drop shadows on cards/bubbles — flat surfaces with hairline borders
  only, no shadow.

## Verification before calling this done

Reload `GET /ui/preview.html`, hard-refresh, and visually compare against
this spec component by component — header, message bubbles, citation
pills, confidence indicator, diff card (trigger a real `/edit` to see it),
input bar, quick-question chips, mode dropdown. Screenshot the result and
describe in `progress/JOURNAL.md` any place a real technical constraint
prevented exactly matching this spec, and why.
