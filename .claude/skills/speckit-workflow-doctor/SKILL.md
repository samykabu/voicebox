---
name: speckit-workflow-doctor
description: Check selected dependencies and available host commands.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: workflow:commands/doctor.md
---

# Sanduq Workflow: doctor

Input: $ARGUMENTS

Read `.specify/extensions/workflow/skills/workflow/SKILL.md` and follow the `doctor` entry point.
Use the current explicit feature or issue. Do not infer issue identity from an unrelated editor tab.
The shared skill owns orchestration; do not run a second pipeline after it returns.