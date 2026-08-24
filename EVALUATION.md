# EVALUATION.md — Test Set & Definition of Done

## Developer-mode test questions (Phase 1)

Manually verify each against real retrieved answers and correct citations:

1. How do I create a custom DocType?
2. How does `frappe.whitelist` work?
3. How do I override a controller in ERPNext?
4. How do I create a server script?
5. How do I create a custom app?
6. What hook should I use to run code after a document is saved?
7. How do I safely migrate a customization to a new ERPNext version?
8. How do I add a custom field to an existing DocType?
9. What's the difference between a Server Script and a Client Script?
10. How do I create a REST API endpoint for a custom DocType?
11. How do child tables work in Frappe?
12. How do I set up a scheduled/background job in Frappe?
13. How do permissions work for a custom DocType?
14. What's the correct way to query the database in a Frappe app (ORM vs
    raw SQL)?
15. How do I debug a validation error on document submit?

## Negative test cases (must correctly decline, not fabricate)

- A question with no relevant match in the corpus (e.g., an unrelated
  general-knowledge question)
- A question about a feature that doesn't exist in ERPNext/Frappe
- A question phrased ambiguously enough that retrieval returns low-relevance
  chunks

## Quality bar for each answer

- Grounded in retrieved content only — no fabricated ERPNext/Frappe
  internals not present in the source material
- Cites specific document(s)/section(s)
- Version-appropriate (does not assume the newest ERPNext version's
  behavior if the corpus spans versions — flag this as a known limitation
  in `progress/CURRENT.md` if version-scoping isn't built yet)

## RAGAS metrics (introduce before declaring Phase 1 done)

Run RAGAS against the test set and record scores for:
- Faithfulness (is the answer supported by retrieved context?)
- Answer relevancy
- Context precision

Log baseline scores in `progress/CURRENT.md`. There's no fixed passing
threshold yet — the point is to have a measured baseline to compare future
changes against, not to eyeball quality.

## Definition of Done — Phase 1

Status as of 2026-08-24 (independently verified + user-accepted; see
`progress/CURRENT.md` for evidence and the two consciously-deferred items):

- [x] ERPNext + Frappe docs ingested, chunked, embedded into Chroma
- [x] All 15 developer questions above answered with correct citations,
      verified manually
- [x] All 3 negative test cases correctly return a "no confident answer"
      response instead of fabricating
- [x] RAGAS baseline scores recorded
- [x] FastAPI service running with the documented request/response contract
- [ ] Minimal Frappe sidebar page sends a question and displays answer +
      sources *(consciously deferred — no bench exists on this machine;
      app code complete per current conventions)*
- [x] `README.md` lets a second person set this up from a clean machine
- [x] `progress/CURRENT.md` accurately reflects state, including known
      issues or shortcuts taken
