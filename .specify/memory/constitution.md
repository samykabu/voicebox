# Voicebox Constitution

## Project Tracking

<!-- Written by /speckit-project-init. Consumed by the `project` extension's sync hooks
     and by spec creation/tracking. Do not edit by hand; re-run init to change it. -->

- **GitHub Project owner**: `samykabu` (user)
- **GitHub Project number**: `10`
- **Board**: Voicebox - https://github.com/users/samykabu/projects/10
- **Repository**: `samykabu/voicebox` (`origin`)
- **Hook mode**: `required` (lifecycle sync runs automatically)
- **Config**: `.specify/extensions/project/config.json`

## Core Principles

### I. Local-First By Default (NON-NEGOTIABLE)

Voice samples, generated audio, captures, transcripts, and model weights MUST remain on
the user's machine unless the user has explicitly enabled a remote path for that specific
data. Every feature MUST work with the network unavailable once its models are cached.

- The backend MUST bind to localhost by default; remote exposure is opt-in configuration.
- No telemetry, analytics, crash reporting, or usage beacon may be added, and none may be
  enabled by default if added under a future amendment.
- Any code path that contacts a remote host MUST be reachable only through a setting the
  user turned on, and MUST fail closed — degrade the feature rather than silently fall
  back to a cloud service.
- The offline guard in `backend/utils/hf_offline_patch.py` MUST keep working: cached
  models load without contacting Hugging Face. Its tests are a release gate, not a
  convenience.

*Rationale*: Local-first is the product's reason to exist against ElevenLabs and
WisprFlow, and biometric voice data is not recoverable once leaked. A regression here is
a product failure, not a bug.

### II. Consent-Bound Voice Synthesis (NON-NEGOTIABLE)

`RESPONSIBLE_USE.md` is binding on this codebase, not advisory. The software cannot
verify voice ownership, so the affordances that keep users honest MUST be preserved.

- No change may remove, bypass, or make harder to notice a responsible-use
  acknowledgement, consent prompt, or AI-generated disclosure surface.
- No feature may be built whose primary purpose is impersonation, voice-authentication
  bypass, or concealing that audio is synthetic.
- Features that broaden reach — batch generation, API surfaces, agent integrations —
  MUST carry the same disclosure and consent affordances as the in-app path.
- Profile import/export MUST preserve provenance metadata rather than stripping it.

*Rationale*: Cloning quality is now good enough to cause real harm. The project accepts
that capability, and in exchange accepts a hard floor on the safeguards shipped with it.

### III. Engine-Agnostic Backend Contract

Every TTS and STT engine MUST be reachable only through the protocols defined in
`backend/backends/base.py`. Engine identity MUST NOT leak upward.

- Adding an engine MUST NOT require edits to route handlers, the shared React frontend,
  or the MCP tool definitions beyond registration and capability declaration.
- Engine-specific behaviour (paralinguistic tags, delivery instructions, preset voices,
  language coverage) MUST be expressed as declared capabilities the caller queries, never
  as `if engine == "..."` branching in `backend/routes/` or `app/`.
- A new engine MUST declare its accelerator support and MUST degrade to CPU or report
  unavailability rather than crash on an unsupported accelerator.
- Heavy dependencies (torch, transformers, mlx) MUST be imported lazily inside functions,
  marked `# lazy: heavy import`, so startup time does not scale with engine count.

*Rationale*: Seven engines ship today and more are queued. The multi-engine architecture
is only an asset while integration stays additive; the `add-tts-engine` agent skill can
only work autonomously against a stable contract.

### IV. Upstream-Trackable Fork Discipline

This repository is a fork of `jamiepine/voicebox` and MUST remain mergeable with it.
Divergence is permitted only where it is deliberate, minimal, and recorded.

- Fork-specific changes MUST fall into a declared category: release and updater identity
  (signing keys, endpoints, download links), fork-specific model support (Arabic F5-TTS /
  Habibi), self-hosted CI wiring, or a feature offered upstream and not yet merged.
- General bug fixes and features SHOULD be shaped so they can be contributed upstream;
  gratuitous refactors that complicate future merges MUST NOT be committed.
- Upstream merges MUST be performed on a dedicated `merge/upstream-main` branch, never
  by rewriting history on `main`.
- Conflicts resolved in favour of fork-specific behaviour MUST be justified in the merge
  commit message so the next merge knows the divergence was intentional.

*Rationale*: The fork carries changes upstream does not want and depends on upstream for
engine work it cannot fund. Both remain true only if merges stay cheap.

### V. Contract-First API And MCP Surface

The REST API and the MCP server at `/mcp` are public product surfaces consumed by
third-party agents and applications. They MUST be treated as contracts.

- Endpoint or MCP tool changes MUST update the Pydantic models, regenerate the TypeScript
  client via `bun run generate:api`, and update `backend/README.md` in the same change.
- Removing or narrowing an endpoint, MCP tool, tool parameter, or response field is a
  breaking change: it MUST be called out in `CHANGELOG.md` and MUST NOT ship in a patch
  release.
- New MCP tool parameters MUST be optional with a behaviour-preserving default so that
  existing agent integrations keep working untouched.
- The generated TypeScript client MUST NOT be hand-edited.

*Rationale*: Agent integrations break silently and their users blame the app, not the
agent. The generated client is the only mechanism keeping frontend and backend honest
about the shape of the API.

## Platform And Performance Constraints

**Language and toolchain floors.** Python 3.12+ (`requires-python = ">=3.12"`),
TypeScript strict mode, Rust stable, Bun as the sole JS package manager and runner. Raising
a floor requires an amendment; lowering one requires an amendment and a migration note.

**Accelerator matrix.** Every generation path MUST work on MLX/Metal (Apple Silicon),
CUDA (NVIDIA), ROCm (AMD), XPU (Intel Arc), and CPU, or MUST declare and enforce its
unsupported accelerators. CPU is the guaranteed fallback and MUST stay functional.

**Startup and responsiveness.** Generation is asynchronous and MUST NOT block the UI. The
serial execution queue preventing GPU contention is a design invariant. Generations
orphaned by a crash MUST auto-recover on startup rather than remain stuck.

**Model handling.** Models are downloaded on demand, cached, and reused. Model downloads
MUST report progress, MUST be resumable or safely re-runnable, and MUST NOT be triggered
implicitly by a code path the user did not ask for.

**Native shell.** The desktop app is Tauri (Rust), not Electron. Global hotkey, paste
injection, and focus introspection stay in the Rust shim. Platform-specific behaviour MUST
degrade gracefully where parity does not yet exist rather than block the build.

## Development Workflow And Quality Gates

**Branching and commits.** Work happens on `feature/`, `fix/`, `docs/`, `chore/`, or
`merge/` branches. `main` is protected in practice: changes land through pull requests.
Commit subjects follow Conventional Commits with a scope — `feat(pronunciation):`,
`fix(models):`, `docs:`.

**Quality gates.** Before a PR is merged the following MUST pass:

| Gate | Command |
|---|---|
| JS/TS lint + format + typecheck | `just check-js` (`bun run check`) |
| TypeScript typecheck (app + web) | `bun run typecheck` |
| Python lint + format | `just check-python` (`ruff check`, `ruff format --check`) |
| Python tests | `just test` (`pytest backend/tests`) |
| Web build smoke test | `bun run build:web` |

Python tests are currently run locally rather than in CI. Until CI executes them, the
author MUST run `just test` before requesting review and MUST say so in the PR. Closing
this gap is a standing obligation, not an accepted permanent state.

**Style.** `backend/STYLE_GUIDE.md` governs Python: ruff-enforced, 120-column, double
quotes, built-in generics and `X | Y` unions (no `typing.List`, no
`from __future__ import annotations`), relative imports within the `backend` package, no
wildcard imports. Biome governs TypeScript: functional components, named exports, strict
mode. `rustfmt` governs Rust, with errors handled explicitly rather than unwrapped.

**Documentation.** `CHANGELOG.md` MUST be updated in the change that alters user-visible
behaviour. API changes MUST update `backend/README.md`. New engines MUST follow
`docs/content/docs/developer/tts-engines.mdx`.

**CI runner policy.** This project runs its CI/CD jobs on **GitHub-hosted runners**
(`ubuntu-latest`, `windows-latest`, `macos-*`). This is a deliberate, repository-scoped
departure from the owner's default self-hosted-runner rule, and it is recorded in red in
`README.md` as that rule requires.

The reason is structural, not preference: the home-office ARC scale sets
(`homek8-general`, `homek8-mobile`) are registered to the `abushanab-net` organisation,
while this repository sits under the `samykabu` personal account, so no job here can ever
reach them. A job targeting `homek8-general` does not fail — it queues forever and its
check never reports, which is worse than not having the check. No self-hosted runner of
any platform is registered for this repository.

- A new or edited workflow MUST target a GitHub-hosted runner unless a self-hosted runner
  is actually registered for this repository at that time.
- `README.md` MUST keep listing every workflow and job with its runner, in red, together
  with what would remove the departure.
- If this repository moves into `abushanab-net`, or a scale set is registered against it,
  the Linux-only jobs MUST move back to `homek8-general`, and this section MUST be amended
  in the same change. The Windows and macOS jobs additionally need self-hosted runners of
  those platforms, which do not exist today.

**Release process.** Releases are cut with `bumpversion` (`.bumpversion.cfg`), which
updates all eight version sites, commits, and tags `v{version}`. Pushing the tag triggers
the release workflow. Release artifacts MUST be cryptographically signed with this fork's
own key, and the updater MUST verify signatures over HTTPS before installing.

**Spec Kit lifecycle.** Feature work follows the Spec Kit flow (specify → plan → tasks →
implement). The `project` extension's sync hooks are `required`: the GitHub Project board
named under Project Tracking is advanced automatically at each lifecycle event, and its
card status is the authoritative view of feature state.

**Security reporting.** Vulnerabilities go to `security@voicebox.sh` per `SECURITY.md` and
MUST NOT be filed as public issues or described in a public PR before disclosure.

## Governance

This constitution supersedes conflicting guidance in `README.md`, `CONTRIBUTING.md`,
`backend/STYLE_GUIDE.md`, agent skills, and prior practice. Where another document is
merely more specific, it stands; where it contradicts a principle here, this document
wins and the other document MUST be corrected.

**Amendment procedure.** Amendments are proposed as a pull request that modifies this file
and nothing else. The PR MUST state the version bump and its rationale, and MUST list any
code, workflow, or documentation changes the amendment makes necessary. Amendments take
effect on merge.

**Versioning policy.** This document is versioned semantically and independently of the
application:

- **MAJOR** — a principle is removed or redefined in a way that permits what it previously
  forbade, or a governance rule is relaxed.
- **MINOR** — a principle or section is added, or existing guidance is materially expanded.
- **PATCH** — clarification, wording, or formatting with no change in obligation.

**Compliance review.** Every pull request MUST be reviewable against this document, and a
reviewer MUST reject a change that violates a principle marked NON-NEGOTIABLE regardless
of its other merits. Complexity that appears to conflict with a principle MUST be
justified in the PR description rather than left for the reader to infer. Principles I and
II admit no exceptions; III, IV, and V admit documented, time-boxed exceptions recorded in
the PR that introduces them.

**Runtime guidance.** Day-to-day development guidance lives in `CONTRIBUTING.md`,
`backend/STYLE_GUIDE.md`, and `docs/PROJECT_STATUS.md`. Agents working in this repository
read this constitution first.

**Version**: 2.0.0 | **Ratified**: 2026-09-22 | **Last Amended**: 2026-09-22
