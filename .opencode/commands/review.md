---
description: Run architecture, code, and security review on recent work
agent: build
---
Recent changes:
!`git log --oneline -15`
!`git diff HEAD~5 --stat 2>/dev/null || echo "fewer than 5 commits"`

Invoke the @architect, @reviewer, and @security subagents against the
current state of the code relevant to these recent changes. Consolidate
their findings into one report, ordered by severity (blocking issues
first). Do not fix anything yet — just report.
