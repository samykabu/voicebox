---
name: speckit-workflow-clarify
description: Read GitHub answers and automatically prepare tasks and implementation.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: workflow:commands/clarify.md
---

# Sanduq Workflow: clarify

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `clarify` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.