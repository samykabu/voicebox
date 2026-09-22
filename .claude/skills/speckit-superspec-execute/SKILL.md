---
name: speckit-superspec-execute
description: Sanduq managed lifecycle overlay
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:workflow
user-invocable: true
disable-model-invocation: false
---

# Speckit Superspec Execute Skill

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
and continue automatically. This overrides upstream instructions to pause for
approval at every routine phase; do not ask again for approvals already recorded.
Explicit HUMAN-REVIEW tasks, unresolved requirements,
security decisions and deployment approvals still pause. Execute small batches
and hand off only at a reliably measured context limit. Without reliable telemetry,
continue automatically; never stop on estimates or reset a measured budget per task.

Continue the applicable upstream domain instructions below.


# speckit.superspec.execute

Orchestrate implementation with TDD, subagents, and review gates.

## Usage

```
/speckit.superspec.execute [spec-number|spec-path]
```

## Process

1. Read the tasks file for the target feature
2. Read the plan and constitution for context
3. **Superpowers detection**: Check for `executing-plans`, `subagent-driven-development`,
   and `test-driven-development` skills
4. Walk through tasks phase by phase:

   **For `[TDD]` tasks**:
   - If TDD skill found, follow its RED-GREEN-REFACTOR process
   - Otherwise: write test → verify it fails → implement → verify it passes → refactor

   **For `[SUBAGENT]` tasks**:
   - If subagent-driven-development skill found, follow its dispatch protocol
   - Otherwise: implement sequentially in-session

   **For `[P]` tasks**:
   - Launch parallel tasks where possible using the Task tool

   **For `[REVIEW]` tasks**:
   - Pause and run review protocol (see `commands/review.md`)

5. At each **phase checkpoint**:
   - Summarize completed work
   - Run tests if applicable
   - Ask user for approval before proceeding to next phase

6. Update task checkboxes in `tasks.md` as each task completes
7. Update `specs/NNN/progress.yml` with current execution state

## Output

Code changes in the project, updated task checkboxes in `tasks.md`.

## Human Checkpoints

The agent MUST pause at every phase boundary and wait for explicit user approval.
Never skip a checkpoint.

## Superpowers Adaptation

| Skill | Adaptation |
|-------|------------|
| `executing-plans` | Follow its batch processing protocol with human checkpoints |
| `subagent-driven-development` | Follow its dispatch protocol for `[SUBAGENT]` tasks |
| `test-driven-development` | Follow its RED-GREEN-REFACTOR discipline for `[TDD]` tasks |

If no superpowers are available, all three fall back to built-in sequential execution
with manual confirmation. See `.specify/extensions/superspec/references/superpowers-bridge.md` for full details.
