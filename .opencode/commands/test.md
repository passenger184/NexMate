---
description: Run the EVALUATION.md test question set against the current pipeline
agent: build
---
Invoke the @tester subagent to run the full test set from @EVALUATION.md
against the current pipeline (service if running, direct pipeline call
otherwise). Report pass/fail per question and overall RAGAS scores if
available. If the phase's Definition of Done checklist is now fully
satisfied, say so explicitly and propose the update to
@progress/CURRENT.md — do not edit it automatically.
