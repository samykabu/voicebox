---
name: speckit-scope-plan
description: Regenerate and validate the implementation dependency plan with Archify after a split.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: scope:commands/plan.md
---

# Refresh implementation plan

Read `.specify/extensions/scope/references/archify-plan.md` and the installed Archify
skill. Execute that workflow; it is mandatory after every published decomposition.
Do not mark Scope complete while `.specify/scope/plan-pending.json` exists.