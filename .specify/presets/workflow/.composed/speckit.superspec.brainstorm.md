---
description: Sanduq managed lifecycle overlay
---


<!-- sanduq-workflow-managed:v1 -->
If `.specify/workflow.yml` is absent, continue with the upstream command unchanged.
Otherwise read `.specify/extensions/workflow/skills/workflow/SKILL.md` and the
checkpoint for the explicitly bound feature. If this invocation has no active
matching stage claim, enter the dispatcher (scope for a new issue, continue for
an existing feature) and STOP this outer invocation when it returns. Inside a
matching claim, execute the domain work below once, then return control to the
dispatcher. Never recursively enter the dispatcher from the claimed command.
The dispatcher alone chooses and calls the next stage. Keep mandatory safety and
binding guards. Disabled hooks stay disabled. Do not independently invoke another
task generator, executor, or PR hook. Use bounded batches. Only reliable measured context can trigger a context pause;
missing, estimated or stale usage must not stop automatic continuation.

Execute `.specify/extensions/scope/skills/github-clarification/SKILL.md` with
engine clarify or brainstorm respectively. This replaces upstream chat questions,
question-count limits and approval loops. Read paginated GitHub answers including
edits. Unchanged unanswered discussions wait without posts. Only resolved and
applied answers advance. Return to the dispatcher rather than calling Plan twice.
When execution.checkpoints is required-only, project policy pre-authorizes
routine phase checkpoints and backend choice. Record the selected execution mode
and continue automatically. Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.

Continue the applicable upstream domain instructions below.



<!-- scope-brainstorm-overlay:start -->
## Managed workflow precedence

When `.specify/workflow.yml` exists, first read the Sanduq workflow policy and
`.specify/extensions/workflow/skills/workflow/SKILL.md`. During an active stage,
return to that dispatcher after the domain work; never independently chain Plan
or stop the entire lifecycle. With `resume_on_reinvoke: reread-answers`, Need
Clarifications allows reading and applying new answers without a manual status
move. If no new human answers or material input changes exist, report waiting
without publishing another round. These managed rules override conflicting
legacy status/stop instructions below. Unmanaged projects retain the old flow.

## Mandatory unattended GitHub brainstorm contract

Read `.specify/extensions/scope/skills/github-clarification/SKILL.md` and execute it
with `engine: brainstorm`. Use the explicit GitHub issue number or the current bound
feature. This shared contract supersedes Superspec's and Superpowers' one-at-a-time
interactive questioning, question quotas, chat approvals, and completion signals.
Do not allow an optional underlying brainstorming skill to reinstate those rules.

Only Feature Specification issues are eligible. Need Clarifications stops immediately
before analysis or new comments; ask the user to answer each GitHub question and move
the issue back to Feature Specification. Keep Superspec's five-category coverage
scan as a minimum, expanding to all material ambiguity categories without a question
count limit. Use the same GitHub history, IDs, answers and round count as Clarify.

Questions are separate GitHub comments mentioning the issue creator, in simple English,
with clear supporting details/diagrams and a highlighted justified AI recommendation.
On a resolved review, execute the shared workflow's `$speckit-plan` handoff automatically
for the same issue and spec. Run the shared workflow including that handoff, then STOP; do not execute the legacy interactive
process afterward. Superspec availability controls auto-selection, not a second round.
<!-- scope-brainstorm-overlay:end -->


# speckit.superspec.brainstorm

Deep-dive edge cases and refine a spec document using brainstorming skills.

## Usage

```
/speckit.superspec.brainstorm [spec-path] [focus-topic]
```

**Example**: `/speckit.superspec.brainstorm specs/001-develop/spec.md "Discuss the Edge Cases in the requirements document and confirm how to resolve these scenarios."`

## Process

1. Read the target spec file
2. Read the constitution for project constraints
3. **Superpowers detection**: Check for `brainstorming` skill
   - **If found**: Read the brainstorming SKILL.md and follow its questioning protocol,
     adapting all outputs to the target spec file
   - **If not found**: Use the built-in 5-category questioning protocol:
     - Boundary conditions (min/max, empty states, edge-of-range)
     - Error scenarios (service down, malformed input, partial failures)
     - Scale & performance (load, concurrency, rate limits)
     - Security & privacy (injection, authorization, data exposure)
     - User experience (confusion points, accessibility, unintended usage)
4. Ask questions **one at a time**, preferring multiple choice format
5. After each answer, update the spec:
   - New requirements → add to Functional Requirements
   - Resolved questions → update Open Questions table
   - New edge cases → add to Edge Cases section
6. When the user confirms the spec is ready, update the "Brainstorm Log" with a
   dated summary of insights discovered

## Output

Updated spec file with refined edge cases, resolved open questions, and brainstorm log entries.

## Iteration

This command can be run multiple times on the same spec. Each session appends to the
brainstorm log and skips previously explored categories.

## Superpowers Adaptation

When using the `brainstorming` skill, adapt its outputs:
- Design documents → fold insights back into the existing `spec.md`
- Output location → write to `specs/NNN/spec.md` (not `docs/superpowers/`)

See `.specify/extensions/superspec/references/superpowers-bridge.md` for full adaptation rules.
