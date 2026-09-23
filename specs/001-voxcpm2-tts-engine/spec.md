# Feature Specification: VoxCPM2 Text-to-Speech Engine

**Feature Branch**: `feature/001-voxcpm2-tts-engine`

**Created**: 2026-09-22

**Status**: Implemented

**Input**: GitHub issue [samykabu/voicebox#13](https://github.com/samykabu/voicebox/issues/13) — scoped at effort 13, kept whole as a single executable issue by explicit user decision.

User description: "Add VoxCPM2 as a first-class TTS engine in Voicebox so that users get an Apache-2.0, 48 kHz, 30-language engine that can both clone a voice from a sample and design one from a written description."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate speech in a language the product could not serve freely before (Priority: P1)

A user who needs Arabic speech for something they intend to publish or sell opens Voicebox, picks the new VoxCPM2 engine, chooses Arabic, types their text, and gets high-quality audio. Today their only broad-dialect Arabic option carries a non-commercial licence, and the commercially safe alternative only speaks Modern Standard Arabic. With this engine they no longer have to choose between licence safety and dialect coverage.

**Why this priority**: This is the reason the feature exists. It removes a licensing dead end that no amount of tuning to the existing engines can fix, and it is the one outcome that is worthless if any other part ships without it.

**Independent Test**: Select VoxCPM2, generate in Arabic and in at least two other supported languages, and confirm the produced audio is intelligible and the engine is presented as permissively licensed. Delivers value on its own even with no cloning and no voice design.

**Acceptance Scenarios**:

1. **Given** a machine that can run the engine, **When** the user opens the engine picker, **Then** VoxCPM2 appears as a selectable option alongside the existing engines.
2. **Given** VoxCPM2 is selected for the first time, **When** the user starts generation or triggers a download, **Then** they are shown the download size and asked to confirm before it starts, and once confirmed a progress indicator appears, reports advancing progress, and completes without the user having to guess whether anything is happening.
3. **Given** the engine is ready, **When** the user generates from text, **Then** speech is produced at the engine's full 48 kHz quality.
4. **Given** the user opens the language selector with VoxCPM2 chosen, **When** the list renders, **Then** exactly the languages this engine supports are offered, and Arabic is among them.
5. **Given** Arabic text containing words covered by the pronunciation dictionary, **When** generation runs, **Then** those words are pronounced as the dictionary specifies.
6. **Given** the user is comparing engines on licensing, **When** they inspect VoxCPM2, **Then** it is shown as permissively licensed and usable commercially.

---

### User Story 2 - Clone a voice with the new engine (Priority: P1)

A user who already has a Voice Profile — one reference clip or several — selects VoxCPM2 and generates in that voice. The result sounds like the person in the reference audio. Repeating the same generation with the same seed gives them the same audio again, so they can iterate on text without the voice drifting underneath them.

**Why this priority**: Cloning is the product's core capability, and an engine that cannot clone is a second-class citizen in this app. It is P1 alongside Story 1 because the licensing win in Story 1 is materially less useful if it only applies to generic voices.

**Independent Test**: Take an existing Voice Profile with one clip and another with several, generate with each under VoxCPM2, and confirm speaker likeness and seed reproducibility. Testable without any voice-design or availability work.

**Acceptance Scenarios**:

1. **Given** a Voice Profile with a single reference clip, **When** the user generates with VoxCPM2, **Then** the output is recognisably the same speaker as the reference.
2. **Given** a Voice Profile with several reference clips, **When** the user generates with VoxCPM2, **Then** all of the clips inform the result and generation succeeds rather than failing or silently using only one.
3. **Given** the user has already generated once with a profile, **When** they generate again with that same profile, **Then** the second generation does not repeat the preparation work the first one already did.
4. **Given** the same text, voice and seed, **When** the user generates twice, **Then** the two results are identical.
5. **Given** the user has finished working with the engine, **When** they unload it, **Then** the memory it held is returned to the machine and the engine reports itself as not loaded.

---

### User Story 3 - Know up front whether this engine can run on this machine (Priority: P2)

A user on hardware that cannot run VoxCPM2 never gets to pick it and then hit a wall. The engine is shown greyed out with a plain sentence explaining why, never hidden. The vendor documents automatic fallback from NVIDIA to Apple Silicon to the processor, so this is expected to be rare; it protects machines that still cannot load the model. They lose nothing and learn something; they do not download several gigabytes to discover the engine will not start.

**Why this priority**: P2. The engine runs on the processor and has an Apple Silicon path, so almost every machine can use it; this story protects the remaining machines that cannot load the model from a crash at the point of use. It was P1 while the engine was believed to exclude every Mac; the dependency probe disproved that and the user moved it to P2 at the T002 decision gate.

**Independent Test**: Run the app on hardware the engine does not support and confirm the engine is visibly greyed out in the picker with a stated reason, not hidden, and that no generation attempt reaches a crash. Testable without cloning or voice design. On real hardware VoxCPM2 is never unavailable today, because it falls back to the processor, so the unavailable path is exercised with an injected engine configuration (see backend/tests/test_cpu_fallback.py and backend/tests/test_engine_capabilities.py).

**Acceptance Scenarios**:

1. **Given** hardware that cannot run VoxCPM2, **When** the user opens the engine picker, **Then** the engine is listed as unavailable, greyed out with a clear, specific reason, and is not hidden.
2. **Given** hardware that cannot run VoxCPM2, **When** the user attempts to reach it by any route, **Then** they receive an explanatory refusal rather than an error, a hang, or a crash.
3. **Given** hardware that can run VoxCPM2, **When** the user opens the engine picker, **Then** the engine is offered normally with no warning.
4. **Given** the engine's hardware requirements, **When** any part of the product needs to know them, **Then** it reads them from the engine's own declaration rather than from a list that has to be kept in sync by hand.

---

### User Story 4 - Create a voice without having any recording (Priority: P3)

A user who wants a particular kind of voice but has nothing to clone from writes a short description of it — an age, a gender, a manner of speaking — and gets speech in a voice matching that description. This is the first way to make a custom voice in Voicebox without supplying audio.

**Why this priority**: P3 because it is genuinely new capability rather than parity, and the feature is coherent and shippable without it. It is the most likely thing to defer if the engine turns out to be harder to land than expected.

**Independent Test**: Create a designed Voice Profile from a written description (no reference audio), select it with an engine that supports voice design, generate, and confirm the voice audibly matches the description. Testable independently of cloning. (Revised 2026-09-23: every generation requires a Voice Profile, so voice design is reached through a designed profile rather than with no profile selected; decided by the user.)

**Acceptance Scenarios**:

1. **Given** no reference audio, **When** the user supplies a written description of a voice and generates, **Then** speech is produced in a voice matching that description.
2. **Given** a user who has only ever cloned voices, **When** they encounter this option, **Then** it is discoverable without reading documentation.

---

### Edge Cases

- A user starts the multi-gigabyte download and cancels it, loses connectivity, or quits the app part way through. The next attempt must resume or restart cleanly rather than leaving the engine permanently half-installed.
- A user selects VoxCPM2 while a different engine is loaded and the machine does not have room for both. The product must not leave the user with two partially loaded engines and no working generation.
- A user picks a language on another engine, then switches to VoxCPM2, and that language is not in this engine's list. The selection must resolve to something valid rather than silently generating in the wrong language.
- A Voice Profile was created with an engine that cannot clone. Selecting VoxCPM2 with that profile must behave predictably rather than producing an unrelated voice.
- The user’s machine can technically run the engine but does not have enough memory for it in practice. The engine stays available rather than being blocked, and the product warns before the download begins when the machine looks short of memory. Memory is not a hard availability check, because how much is free changes with whatever else is running.
- A written voice description is supplied at the same time as a Voice Profile with reference audio. The reference audio wins, and the interface states plainly that the written description is not being used.
- Arabic text is supplied with a written voice description written in a different language. Any language is accepted for the description. The real behaviour is confirmed during implementation and documented as a known limitation if it works poorly, rather than being restricted in advance.

## Requirements *(mandatory)*

### Functional Requirements

**Availability and selection**

- **FR-001**: The product MUST offer VoxCPM2 as a selectable speech engine wherever the existing engines are offered.
- **FR-002**: The product MUST declare, as part of the engine's own description, which hardware the engine can run on.
- **FR-003**: On hardware that cannot run the engine, the product MUST show it as visibly unavailable with a specific reason wherever engines are listed, rather than hiding it, and MUST NOT allow a user to reach a failed generation through it.
- **FR-004**: Any part of the product that needs the engine's hardware requirements or language coverage MUST obtain them from the engine's declaration rather than from a separately maintained list.
- **FR-005**: The product MUST present the engine's licence and its suitability for commercial use, as it does for the existing engines.

**Generation**

- **FR-006**: Users MUST be able to generate speech from text with this engine at its full 48 kHz output quality.
- **FR-007**: The product MUST offer exactly the languages this engine supports when it is selected, and that set MUST include Arabic.
- **FR-008**: Arabic generation MUST respect the existing pronunciation dictionary.
- **FR-009**: Given the same text, voice and seed, the product MUST produce the same audio every time.
- **FR-010**: The engine MUST use sensible, deliberately chosen defaults for its generation-quality settings, and MUST expose those settings as advanced controls with the chosen defaults preselected.

**Voice cloning**

- **FR-011**: Users MUST be able to generate in a cloned voice from an existing Voice Profile with this engine.
- **FR-012**: The product MUST support Voice Profiles holding several reference clips with this engine, using all of them rather than an arbitrary one.
- **FR-013**: The product MUST avoid repeating reference-audio preparation work it has already done for the same profile.
- **FR-014**: The product MUST treat this engine as cloning-capable everywhere it distinguishes cloning engines from non-cloning ones.

**Voice design**

- **FR-015**: Users MUST be able to produce a voice from a written description without supplying any reference audio, through its own clearly labelled input, distinct from the existing delivery-instruction field and shown only for engines that support it.
- **FR-015a**: Users MUST be able to create a designed Voice Profile from a written description alone, as a third profile source beside cloning and built-in voices, offered only for engines that support voice design. When a generation using a designed profile supplies no separate voice description, the profile's own description is used. Added 2026-09-23 by user decision so that FR-015 is reachable from the app.

**Model lifecycle**

- **FR-016**: The product MUST show download progress for this engine's model, as it does for other engines.
- **FR-017**: Users MUST be able to unload the engine and recover the memory it was holding.
- **FR-018**: The product MUST measure this engine’s real download size and report it accurately, and MUST ask the user to confirm before starting the download for this engine.

**Installation and packaging**

- **FR-019**: Setting up the project from a clean checkout MUST succeed on both Windows and Linux with this engine included, without breaking the existing engines' dependencies.
- **FR-020**: The packaged desktop application MUST still build and start with this engine registered.

**Documentation**

- **FR-021**: The product's engine documentation and model-management documentation MUST cover this engine.
- **FR-022**: The user-visible addition MUST be recorded in the project changelog.

### Resolved scope decisions

- **FR-023**: The engine MUST honour the product's processor-fallback expectation like every other engine: it runs on the processor where no supported accelerator is present. The earlier exception allowing an accelerator-only engine is withdrawn, because the dependency probe confirmed a working processor path (decided by the user at T002).
- **FR-024**: This feature MUST build the smallest workable capability channel: the engine declares its supported hardware and languages, those declarations are exposed, and the interface reads them for this engine. The seven existing engines keep their current hand-maintained lists and MUST NOT be migrated as part of this feature. Because this introduces an interface between the backend and the app, the product’s contract rules for such an interface apply within the same change.

### Responsible use (Principle II)

- **FR-025**: The profile creation dialog MUST show a responsible-use acknowledgement, stating that users may only create voices they have the right to use and linking to the Responsible Use guidance, for every profile source (clone, built-in and described). Decided by the user at the T037 consent review, 2026-09-23.
- **FR-026**: Every audio file or audio response that Voicebox generates MUST carry an "AI-generated by Voicebox" disclosure in its metadata, for every engine and every surface (saved files, streamed or non-persisted API responses, and effect previews), whether the voice was cloned, built-in or designed. Audio the user recorded or uploaded themselves, such as reference samples, MUST NOT be labelled AI-generated. Decided by the user at the T037 consent review and refined after T051, 2026-09-23.
- **FR-027**: Voice profile export MUST preserve provenance: the profile's voice type, its written description where it has one, and its default engine. Import MUST restore them rather than rebuilding every profile as cloned, and a designed profile with no audio samples MUST be exportable. Decided by the user at the T037 consent review, 2026-09-23.

### Key Entities

- **Speech engine**: A named way of turning text into audio. Carries its own identity, display name, licence and commercial-use status, supported languages, download size, and — new with this feature — the hardware it can run on, whether it can clone, and whether it can create a voice from a written description (its voice-design capability).
- **Voice profile**: A user-created voice. Existing entity, with three sources: cloned (one or more reference audio clips and their transcripts), preset (a built-in voice of a specific engine), and designed (a written description, new in use with this feature, offered only for engines with the voice-design capability). This feature makes cloned and designed profiles usable with the new engine.
- **Voice description**: A short written description of a desired voice, used in place of reference audio. It is either stored on a designed profile or supplied once with a generation. New with this feature.
- **Prepared voice reference**: The reusable result of processing a profile's reference audio for a particular engine, kept so the same work is not repeated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a commercial use case can generate broad-dialect Arabic speech under a permissive licence, which is impossible today with any single option in the product.
- **SC-002**: A listener familiar with the reference speaker identifies a VoxCPM2-cloned generation as that speaker in at least 4 of 5 blind attempts.
- **SC-003**: 100% of repeat generations with an unchanged text, voice and seed produce identical audio.
- **SC-004**: On hardware that cannot run the engine, 0% of user attempts to use it end in a crash, a hang, or an unexplained error; every attempt ends in a stated reason.
- **SC-005**: A user who has never made a custom voice can produce one from a written description without consulting documentation.
- **SC-006**: A first-time user is told how large the download is and confirms it before it starts, and can see it progressing once it does.
- **SC-007**: Project setup from a clean checkout succeeds on both supported desktop platforms, and every engine that worked before this change still works after it.
- **SC-008**: The packaged desktop application still builds and starts.
- **SC-009**: Adding this engine required no new hand-maintained per-engine list in the user interface; its hardware support and languages are read from the engine’s own declaration.

## Assumptions

- The engine is added alongside the existing engines. Nothing that works today stops working, and no existing engine, model or voice is removed or replaced.
- Only one size of this model ships. Users are not asked to choose between variants of it, so none of the product's model-size machinery is involved.
- Streaming generation is not part of this feature; generation behaves like the product's other chunked engines.
- Reference audio, generated audio and model weights stay on the user's machine, as with every other engine. This feature introduces no new remote path.
- Voicebox had no in-app consent prompt, responsible-use acknowledgement or AI-generated disclosure before this feature, for cloning or any other path (confirmed by the T037 survey, 2026-09-23). This feature adds them for every path through FR-025 to FR-027, rather than assuming they already exist.
- The existing Voice Profile, pronunciation dictionary, download-progress and model-unload mechanisms are reused rather than rebuilt.
- In v1, custom advanced generation settings (FR-010) apply to the generation they were chosen for. Regenerate, retry and the `/speak` API use the engine's declared default settings, because the settings are not stored with a generation. Reproducing a generation made with non-default settings therefore requires choosing the same settings again. Decided by the user on 2026-09-23; persisting them is a follow-up.
- Reproducibility (FR-009) is expected to hold for a given machine and engine version, not across different hardware or a future version of the model.
- "Recognisable speaker likeness" is judged by human listening, not by an automated similarity score, since the product ships no such score today.
- This repository is a fork that must stay cheaply mergeable with its upstream, so the change is expected to stay additive.
- The project's Python version floor is unchanged by this feature; changing it would require amending the constitution separately.
- The automated test suite for this area runs locally rather than in continuous integration, so verification of this feature is attested by the author at review time.

## Dependencies

- Availability of the third-party VoxCPM2 model and its distribution package, under the Apache-2.0 terms described in the source issue.
- The outcome of the dependency and platform probe that the source issue requires before implementation: it resolves FR-018 and FR-023, and informs FR-019.
- The existing pronunciation dictionary behaviour introduced in [PR #11](https://github.com/samykabu/voicebox/pull/11), which FR-008 depends on.


<!-- speckit-clarification:spec a52edb4789bf2af8be81 -->
### GitHub clarification review 1



<!-- speckit-clarification:spec 328cc7630b9b368f2129 -->
### GitHub clarification review 2

- C1Q1: answered. Checkbox selection A, exactly one original option checked on the question comment. Ship on supported hardware with a clear unavailable state everywhere else. Resolves FR-023: an accelerator-only engine is accepted as a deliberate, declared exception to the processor-fallback expectation, conditional on the unavailable state being explicit. Applied to FR-023 and reinforced by the FR-003 edit. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781571879
  Checkbox selection observed: A — Ship it on supported hardware, with a clear unavailable state everywhere else.
  Superseded at T002 (2026-09-23): the exception is withdrawn, and FR-023 now requires processor fallback, because the probe confirmed a working processor path (evidence/probe.md, "T002 decisions").
- C1Q2: answered. Checkbox selection A, exactly one original option checked on the question comment. Build the smallest real capability channel and use it for VoxCPM2 only. Resolves FR-024: the feature builds the declared-capability mechanism rather than recording a divergence, and explicitly does not migrate the seven existing engines. Applied to FR-024 and to SC-009, whose conditional qualifier is now removed. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781572294
  Checkbox selection observed: A — Build the smallest real channel and use it for VoxCPM2 only.
- C1Q3: answered. Checkbox selection A, exactly one original option checked on the question comment. Show the engine greyed out everywhere with a specific reason. Resolves the hidden-or-disabled ambiguity that made User Story 3 untestable. Applied to FR-003, which previously permitted either behaviour. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781572643
  Checkbox selection observed: A — Show it greyed out everywhere, with a specific reason.
- C1Q4: answered. Checkbox selection B, exactly one original option checked on the question comment. Offer the engine but warn before the download when memory looks insufficient. Resolves the insufficient-memory edge case: memory is explicitly not a hard availability gate, because free memory varies with what else is running. Applied to the edge case entry. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781573028
  Checkbox selection observed: B — Offer it, but warn before the download when memory looks insufficient.
- C1Q5: answered. Checkbox selection A, exactly one original option checked on the question comment. Give voice-from-description its own labelled input, shown only for engines that support it. Resolves FR-015 against the source issue’s original suggestion of reusing the delivery-instruction field, on the grounds that describing a speaker and directing a performance are different things. Applied to FR-015. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781573432
  Checkbox selection observed: A — Give it its own labelled input, shown only for engines that support it.
- C1Q6: answered. Checkbox selection A, exactly one original option checked on the question comment. The reference recording wins and the interface says the description is unused. Resolves the conflicting-voice-inputs edge case so the outcome is deterministic rather than decided by evaluation order. Applied to the edge case entry. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781573818
  Checkbox selection observed: A — The reference recording wins; show that the description is not in use.
- C1Q7: answered. Checkbox selection A, exactly one original option checked on the question comment. Show the size and confirm before downloading, for this engine. Resolves FR-018’s open half: the size must be measured, and this engine alone gets a confirmation step because it is far larger than any other. Applied to FR-018 and to SC-006. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781574152
  Checkbox selection observed: A — Show the size and confirm before downloading, for this engine.
- C1Q8: answered. Checkbox selection B, exactly one original option checked on the question comment. Expose the generation-quality settings as advanced controls with the chosen defaults preselected. This is the one answer that differs from the AI recommendation, which was to fix them for this release. Recorded as chosen, not as recommended. Applied to FR-010. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781574482
  Checkbox selection observed: B — Expose them as advanced settings with the chosen defaults preselected.
- C1Q9: answered. Checkbox selection A, exactly one original option checked on the question comment. Allow any language for the voice description and document the real behaviour once known. Resolves the description-language edge case without imposing a restriction before evidence exists. Applied to the edge case entry. Evidence: https://github.com/samykabu/voicebox/issues/13#issuecomment-5781574948
  Checkbox selection observed: A — Allow any language; document the real behaviour once it is known.
