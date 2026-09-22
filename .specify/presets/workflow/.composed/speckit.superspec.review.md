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

When execution.checkpoints is required-only, project policy pre-authorizes
routine phase checkpoints and backend choice. Record the selected execution mode
and continue automatically. Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.

Continue the applicable upstream domain instructions below.


# speckit.superspec.review

Run code review against spec requirements using review skills.

## Usage

```
/speckit.superspec.review [scope]
```

**Scope**: Optional file paths, spec number, or "all changes". Defaults to the latest feature.

## Process

1. Read the spec and plan for the feature being reviewed
2. **Superpowers detection**: Check for `requesting-code-review` skill
   - **If found**: Read the skill and follow its pre-evaluation checklist and review
     dispatch protocol
   - **If not found**: Use the built-in review protocol below
3. Built-in review protocol:
   - **Spec compliance**: Verify each acceptance scenario from the spec is implemented
   - **Edge case coverage**: Verify brainstormed edge cases are handled
   - **Constitution compliance**: Check all governance principles are respected
   - **Code quality**: Check for bugs, security issues, error handling
   - **Test coverage**: Verify tests exist for critical paths
4. Report findings with confidence scores (0-100, only report issues >= 80)
5. Group findings by severity: Critical > Important > Suggestion

## Output

Review findings reported to user. Optionally written to
`specs/NNN-feature-name/checklist-review.md`.

## Finding Format

Each finding includes:
- Clear description with confidence score
- File path and line reference
- Specific recommendation or fix suggestion

Findings below 80 confidence are suppressed to reduce noise.

## Superpowers Adaptation

When using the `requesting-code-review` skill, adapt its outputs:
- Add superspec-specific review dimensions: spec compliance, constitution compliance,
  brainstorm coverage
- Output location → report to user, optionally write to checklist file

See `.specify/extensions/superspec/references/superpowers-bridge.md` for full adaptation rules.
