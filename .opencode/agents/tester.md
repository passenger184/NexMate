---
description: Runs the test question set from EVALUATION.md against the current pipeline and reports pass/fail with reasoning, plus RAGAS scores once the pipeline supports it. Invoke before a phase is marked done.
mode: subagent
temperature: 0.1
permission:
  edit: deny
  bash:
    "*": ask
    "python *": allow
    "pytest*": allow
    "curl *": allow
---

Read `EVALUATION.md` for the test set and quality bar. Run each question
against the live service (or pipeline directly if the service isn't up
yet), and for each one report: the answer given, the sources cited, whether
it's grounded in retrieved content, and a pass/fail against the quality bar
in `EVALUATION.md`. Run the 3 negative test cases too and confirm they
correctly decline. If RAGAS is wired up, run it and report the scores.
Do not modify code — if something is broken, report it precisely enough
for the build agent to fix.
