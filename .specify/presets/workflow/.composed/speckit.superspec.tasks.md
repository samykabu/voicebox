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

When revalidating an existing tasks.md, reconcile only changed requirements. Keep
stable task IDs, completed checkboxes, execution markers and native issue mappings
for unchanged work. Add or reopen genuinely changed work with a recorded reason;
do not renumber the feature or reset all progress.

Continue the applicable upstream domain instructions below.


# speckit.superspec.tasks

Generate a phased task breakdown using writing-plans skills.

## Usage

```
/speckit.superspec.tasks [spec-number|spec-path]
```

## Process

1. Read the spec, plan, and constitution for the target feature
2. Read the template at `.specify/templates/tasks-template.md`
3. **Superpowers detection**: Check for `writing-plans` skill
   - **If found**: Read the writing-plans SKILL.md and follow its task decomposition
     process, adapting outputs to the tasks template structure
   - **If not found**: Decompose directly from the plan using the template
4. Organize tasks by phase: Setup → Foundational → User Stories (by priority) → Polish
5. Apply execution markers to each task:
   - `[P]` — can run in parallel (different files, no dependencies)
   - `[TDD]` — must follow RED-GREEN-REFACTOR discipline
   - `[REVIEW]` — requires code review before proceeding
   - `[SUBAGENT]` — can be delegated to a subagent
6. Define phase dependencies and checkpoint gates
7. Write to `specs/NNN-feature-name/tasks.md`

## Output

`specs/NNN-feature-name/tasks.md` with phased task breakdown.

## Execution Markers

| Marker | Meaning | Behavior |
|--------|---------|----------|
| `[P]` | Parallel | Can run concurrently with other `[P]` tasks |
| `[TDD]` | Test-Driven | Must follow RED-GREEN-REFACTOR: write test → fail → implement → pass |
| `[REVIEW]` | Review Gate | Pause for human code review before proceeding |
| `[SUBAGENT]` | Subagent | Can be dispatched to a parallel subagent |

## Superpowers Adaptation

When using the `writing-plans` skill, adapt its outputs:
- Implementation blueprints → merge into `specs/NNN/tasks.md` using template structure
- Task dependencies → map to the Dependencies section
- Parallel opportunities → mark with `[P]` and `[SUBAGENT]`

See `.specify/extensions/superspec/references/superpowers-bridge.md` for full adaptation rules.
