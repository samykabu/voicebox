# Post-merge verification: VoxCPM2 feature

- PR: https://github.com/samykabu/voicebox/pull/73, merged 2026-09-23T19:35:29Z by samykabu into `main` (merge commit).
- Final PR head: 2a7bcfa4164cb0679e2f9b7088080622d0c94258. Checks on it: frontend-quality pass, workflow-evidence pass.
- Merge commit: 8e931e9ea3b5824dcff1417520aad6ddeb8a6bf3. Push CI run "CI" (frontend-quality) on it: completed, success.
- Issue #13: closed as completed by the PR. All 56 task sub-issues closed. Project board item for #13 set to Done.
- Human gates recorded: listening check (evidence/human/listening-check.md), final UI review T045 (evidence/human/final-review-t045.md), designed long-text listening check I3 (evidence/human/listening-check-i3.md).
- Deployment: none. Desktop releases ship through release.yml on tags; this merge cut no release.
- Follow-ups: imported `instruct` length and `language` pattern are not validated (pre-existing); Windows `just setup` picks the system Python; .dockerignore does not exclude backend/venv; the Dockerfile lacks f5-tts and habibi-tts; the E2E harness crashes on cp1252 consoles; the API reference docs need regenerating.
