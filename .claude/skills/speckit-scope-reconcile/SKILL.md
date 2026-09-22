---
name: speckit-scope-reconcile
description: Refresh native scope parent progress after child lifecycle changes.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: scope:commands/reconcile.md
---

# Reconcile scope parents

Run `python .specify/extensions/scope/scripts/scope.py reconcile --apply`.
Report actual changes or a read/authentication error. Parent progress tables include
all native children. Only all-Done descendants permit a parent to become Done and
close as completed. A reopened child reopens its scope ancestors. Do not apply this
policy to arbitrary epics without a Scope parent receipt.