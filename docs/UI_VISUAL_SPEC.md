# docs/UI_VISUAL_SPEC.md — Visual Design Direction

This governs colors, type, and visual personality. `docs/UI_SPEC.md`
already covers structure/behavior (layout, states, diff approval flow) —
implement that structure using the visual language defined here. Do not
default to a generic "AI chatbot" look (soft gradients, a single bright
accent on near-black, identical rounded cards with drop shadows,
tracked-out ALL-CAPS labels, a '→' on every button). This is a diagnostic
tool for ERP developers, not a consumer chat app — it should look and feel
like it belongs next to code and error logs, not next to a customer-support
widget.

## Concept

ERP systems have a real visual heritage: terminal screens, status boards,
diagnostic panels — amber/green phosphor displays in old POS and inventory
systems, dense information density, no decoration for its own sake. Lean
into that lineage, modernized: this should feel like a **diagnostic
instrument panel built into ERPNext's own control room**, not a friendly
mascot bot bolted onto the side. Confidence and status are read like gauge
readings, not badges. Density and clarity over whitespace-heavy SaaS
polish — the audience is a developer mid-debug, not a browsing customer.

## Color

Deep ink-navy base (not pure black — pure black next to Frappe Desk's own
light chrome looks like a hole in the page), warm amber as the single
accent (the terminal-heritage nod), muted teal for "this is trustworthy"
and warm rust for "treat this with suspicion" — status colors that read as
instrument-panel signals, not generic green/red alert colors.

| Token | Hex | Role |
|---|---|---|
| `--surface-base` | `#12141C` | Panel background |
| `--surface-raised` | `#1B1E29` | Message groups, input bar, code blocks |
| `--border-hairline` | `#2A2E3D` | Dividers, card outlines — hairline only, no shadows |
| `--text-primary` | `#EDEFF5` | Body text |
| `--text-muted` | `#8B90A3` | Timestamps, secondary labels, citation pills |
| `--accent-amber` | `#E3A23C` | Primary accent — user message tint, active states, links |
| `--signal-trust` | `#4FA989` | High confidence, successful commit |
| `--signal-caution` | `#D9764A` | Low confidence / no-match / refused edit |
| `--code-diff-add` | `#4FA989` (12% fill) | Added lines in diff view |
| `--code-diff-remove` | `#D9764A` (12% fill) | Removed lines in diff view |

Do not add a second bright accent color "for variety" — amber carries all
primary emphasis; the two signal colors are reserved strictly for
confidence/status, never used decoratively.

## Type

- **UI text**: a clean grotesk sans already consistent with Frappe Desk's
  own typography (check what Desk actually uses and match it — this tool
  should not visually clash with the app it lives inside). Do not introduce
  an unrelated display face for headers; there's no marketing headline
  here, just an interface.
- **Code, diffs, citations' file paths**: a real monospace face (e.g.
  `JetBrains Mono` or `IBM Plex Mono`) — this is a developer tool, code
  should look like code, not like the surrounding prose.
- Two type roles total (UI sans + code mono). No third "personality" font.
- No tracked-out ALL-CAPS labels anywhere. Section labels use normal case,
  distinguished by the muted text color and size, not by shouting.

## Layout personality

- Flat surfaces with hairline borders for structure — not identical
  rounded cards with soft drop shadows stacked on top of each other. A
  message doesn't need a bounding card at all (see `docs/UI_SPEC.md`); the
  diff-approval block and citation pills are the only elements that get a
  visible border, because they're actionable, not just informational.
- Confidence reads as a small inline signal (a colored dot + short label),
  not a pill-shaped badge — closer to a status LED than a marketing chip.
- The diff view should look like a real terminal diff (monospace, colored
  gutters per `--code-diff-add`/`--code-diff-remove`), not a generic
  "code preview card."

## Motion

One deliberate moment: the panel's slide-in when opened (short, decisive
easing — not a bouncy spring). Beyond that, motion only responds to a
user action:
- A new message fades up gently as it streams in — no per-message
  slide/bounce theatrics.
- Approving a diff gives a brief, satisfying color sweep confirming the
  commit — this is the one place a little flourish is earned, since it's
  confirming something consequential (code just changed).
- Respect reduced-motion preferences — disable the above for users who've
  set that OS/browser preference.

## What to explicitly avoid

- The warm-cream-background-with-serif-and-terracotta look, and the
  near-black-with-neon-accent look — both are the current generic-AI-app
  defaults, and neither fits an ERP diagnostic tool.
- Rounded cards with `rgba(0,0,0,.1)` drop shadows on every element.
- Gradient washes as decoration.
- A '→' appended to button text, middle-dot-joined meta strings, or any
  tracked-out ALL-CAPS eyebrow labels.

## Before building: self-check

Before writing CSS, restate this plan in your own words and check it
against the avoid-list above — if any part of your plan matches a generic
default rather than something grounded in the ERP-diagnostic concept,
revise it and note what changed and why in `progress/JOURNAL.md`. Spend
the one bold visual choice (the amber accent + terminal-diff styling) with
everything else quiet and disciplined — don't add a second attention-
grabbing element competing with it.
