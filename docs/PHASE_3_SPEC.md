# docs/PHASE_3_SPEC.md — Company Knowledge (This Project)

**Do not start until Phase 2's Definition of Done is met.**

## Goal

Add this project's own custom app source code and any internal
documentation (configs, workflows, procedures, troubleshooting notes) into
the same Chroma store used for Phase 1's public docs — tagged so retrieval
can distinguish `public_doc` from `company_doc`/`our_code`, per
`ARCHITECTURE.md`'s knowledge-layering note. No workspace concept needed —
this is still the one project.

## What to ingest

- This project's custom Frappe app source code (function/class-boundary
  chunking is enough for now — don't introduce `tree-sitter` unless simple
  chunking proves inadequate)
- Any internal docs the user has written down (ask what exists — don't
  assume a docs folder structure)

## Retrieval behavior change

Developer questions should now be able to answer from company code, not
just public docs — e.g. "why does this validation fail" should be able to
cite the actual custom validation function, not just generic Frappe
validation docs. Citations must distinguish source type clearly (e.g. "from
your `custom_app/validations.py`" vs. "from Frappe framework docs").

## Definition of Done

- [ ] Custom app source code ingested and retrievable
- [ ] At least 5 questions specific to this project's actual customizations
      answered correctly with citations pointing to the right source
      (company code vs. public docs correctly distinguished)
- [ ] A question that could be answered by either public docs or company
      code correctly prefers/cites the more specific company-code answer
- [ ] `progress/CURRENT.md` and `DECISIONS.md` updated with what was
      ingested and any chunking issues discovered
