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


Continue the applicable upstream domain instructions below.



# Speckit Scope

Input: $ARGUMENTS

Read and execute `.specify/extensions/scope/skills/scope-analyst/SKILL.md`.
Pass the user's issue number or exact title. Missing input is an error, never an
invitation to choose an issue from the active editor, branch, or recent conversation.
In a managed project, return the completed scope evidence to the workflow dispatcher,
which automatically invokes Specify when no unresolved decision remains. Existing
keep-together policy settles decomposition inside its configured effort band.
In an unmanaged project, use the analyst skill as the authority and leave the
enriched Specify prompt ready for the next step.
