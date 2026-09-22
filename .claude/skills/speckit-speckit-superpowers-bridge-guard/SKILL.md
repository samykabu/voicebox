---
name: speckit-speckit-superpowers-bridge-guard
description: Respect the managed workflow execution owner
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:workflow
user-invocable: true
disable-model-invocation: false
---

# Speckit Speckit Superpowers Bridge Guard Skill

<!-- sanduq-workflow-legacy-guard:v1 -->
If `.specify/workflow.yml` exists, the Sanduq dispatcher owns lifecycle transitions.
Run workflow doctor first. An executing or blocked legacy handoff must be inspected
and reconciled from actual evidence; never change it to complete merely to pass a
guard. Do not start a second executor or write another legacy handoff. For execute,
invoke `speckit.workflow.continue` for the explicitly bound feature and return.
For guard/handoff, report the managed owner and return without mutating legacy state.
STOP this invocation before the upstream legacy instructions below. Unmanaged
projects retain those upstream instructions unchanged.



# Superpowers Bridge Guard

Block commands that would overlap Spec Kit / Superpowers responsibilities. The guard reads `.specify/superpowers-handoff.json` and (when needed) the active feature directory, then evaluates a small fixed rule set.

## Rules (hardcoded; see `.specify/extensions/speckit-superpowers-bridge/scripts/powershell/guard-command.ps1` and `.specify/extensions/speckit-superpowers-bridge/scripts/bash/guard-command.sh`)

The guard evaluates these 5 rules in order; the first match wins:

1. **Deny** `speckit.implement` when handoff status is `executing`.
2. **Deny** `superpowers:writing-plans` or `superpowers:brainstorming` when the active feature directory has both `spec.md` AND `plan.md`.
3. **Deny** `speckit.constitution` when handoff status is `executing` (set the handoff to `blocked` first to repair the constitution).
4. **Allow** any other `speckit.*` action — design and clarification commands are always permitted.
5. **Default allow** for anything not matched above.

There is no disposition matrix and no JSON config; adding a rule is a one-line `if`/`elseif` edit. Every allow / deny decision is appended to `.specify/bridge-events.jsonl`.

## Execution

Map the triggering hook or requested skill to an action and run the platform flavor selected by `.specify/init-options.json.script`.

```powershell
.\.specify\extensions\speckit-superpowers-bridge\scripts\powershell\guard-command.ps1 -Action <action> -Actor <codex|claude|unknown>
```

```bash
bash .specify/extensions/speckit-superpowers-bridge/scripts/bash/guard-command.sh --action <action> --actor <codex|claude|unknown>
```

Exit codes: `0` = allow, non-zero = deny (the reason is printed to stdout and recorded in `bridge-events.jsonl`).

## Examples

```powershell
# Denied while handoff is executing
.\.specify\extensions\speckit-superpowers-bridge\scripts\powershell\guard-command.ps1 -Action speckit.implement -Actor claude

# Allowed (Spec Kit design surface is always allowed)
.\.specify\extensions\speckit-superpowers-bridge\scripts\powershell\guard-command.ps1 -Action speckit.tasks -Actor codex

# Denied when an active feature has spec.md + plan.md
.\.specify\extensions\speckit-superpowers-bridge\scripts\powershell\guard-command.ps1 -Action "superpowers:writing-plans" -Actor claude
```
