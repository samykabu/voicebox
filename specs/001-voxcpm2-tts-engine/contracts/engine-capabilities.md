# Contract: Engine Capabilities

**Feature**: `specs/001-voxcpm2-tts-engine` | **Status**: implemented; contract shape reviewed at T010 (2026-09-23)

This is the capability channel required by FR-004 and FR-024 and settled by clarification
C1Q2 ("build the smallest real channel and use it for VoxCPM2 only"). It exists because
nothing in the product carries engine capability from the backend to the app today: the
app keeps its own hardcoded engine list in
[EngineModelSelector.tsx](../../../app/src/components/Generation/EngineModelSelector.tsx#L23)
and its own language map in
[languages.ts](../../../app/src/lib/constants/languages.ts#L65), and no route reads
`TTS_ENGINES` at all.

This contract is additive. No existing endpoint, field or MCP tool is removed or narrowed,
so it is not a breaking change under Principle V.

---

## Scope boundary

This channel serves **VoxCPM2 only** in this feature. The seven existing engines keep their
current app-side lists and are not migrated — an explicit exclusion in the specification,
kept deliberately so the upstream merge surface stays small (Principle IV). The endpoint
still returns every engine, so a later change can migrate the rest without another contract
revision; the app simply does not consume it for them yet.

---

## Endpoint

```http
GET /models/engines
```

Read-only. No parameters. No authentication beyond whatever the backend already applies.

### Response

```json
{
  "engines": [
    {
      "engine": "voxcpm",
      "display_name": "VoxCPM2",
      "available": true,
      "reason": null,
      "warning": "This machine has about 4 GB of graphics memory. VoxCPM2 (Multilingual, Voice Design) usually needs about 6 GB, so generation may fail.",
      "supported_accelerators": ["cuda", "mps", "cpu"],
      "detected_accelerator": "cuda",
      "languages": ["zh", "en", "ar", "..."],
      "supports_cloning": true,
      "supports_voice_design": true,
      "requires_download_confirmation": true,
      "advanced_settings": [
        {"name": "cfg_value", "label": "Guidance", "default": 2.0, "min": 1.0, "max": 3.0},
        {"name": "inference_timesteps", "label": "Quality steps", "default": 10.0, "min": 4.0, "max": 30.0}
      ],
      "size_mb": 4961,
      "license_id": "Apache-2.0",
      "commercial_use": true
    }
  ]
}
```

### Field contract

| Field | Type | Rules |
| --- | --- | --- |
| `engine` | `string` | Stable identifier. Matches the engine regex in `backend/models.py`. |
| `display_name` | `string` | The engine's name from `TTS_ENGINES` (for example "TADA"), not a model variant's name. |
| `available` | `boolean` | False only when the detected accelerator is not in `supported_accelerators` **and** `"cpu"` is not declared either. When `"cpu"` is declared, the engine stays available and runs on the processor, with a `warning` saying so (FR-023; VoxCPM2 on an Intel XPU or DirectML machine). Memory is never a hard gate (C1Q4). |
| `reason` | `string \| null` | Non-null **if and only if** `available` is false. A specific, user-facing sentence — FR-003 forbids a bare disabled control with no explanation. |
| `warning` | `string \| null` | Non-null when the engine is usable but the machine looks marginal: memory below `min_memory_mb`, or a processor fallback because the detected accelerator is not declared. Advisory only; never blocks. |
| `supported_accelerators` | `string[]` | Echo of the declaration. An **empty array means unconstrained**, which is how all seven existing engines report, preserving today's behaviour exactly. |
| `detected_accelerator` | `string` | What this machine actually resolved to via `get_torch_device`. Lets the UI explain the mismatch. |
| `languages` | `string[]` | The union of languages across **all** of the engine's model variants, in a stable order. Replaces the app's hardcoded per-engine map for this engine (FR-007). |
| `supports_cloning` | `boolean` | Derived from `CLONING_ENGINES`. |
| `supports_voice_design` | `boolean` | True only for engines accepting a written voice description. Drives whether the FR-015 input is shown at all. |
| `requires_download_confirmation` | `boolean` | When true, the app asks the user to confirm before downloading (FR-018, C1Q7). False for every existing engine. |
| `advanced_settings` | `object[]` | Settings the app may show as advanced controls, each with `name`, `label`, `default`, `min`, `max`, all numbers serialised as floats (FR-010, C1Q8). Empty for every existing engine. VoxCPM2 declares `cfg_value` 1.0–3.0 (default 2.0) and `inference_timesteps` 4–30 (default 10): the "recommended" ranges in voxcpm 2.0.3 `cli.py`, declared at `backend/backends/__init__.py:548-549`. |
| `size_mb` | `integer` | Download size of the engine's **default** variant, the one downloaded by default. Shown in the FR-018 confirmation dialog. |
| `license_id` | `string \| null` | The value shared by all of the engine's variants; `null` when they disagree (for example F5-TTS, whose Habibi variants mix Apache-2.0 and CC-BY-NC-SA-4.0), so no caller is told a variant is commercial when it is not. |
| `commercial_use` | `boolean \| null` | Same rule as `license_id`. |

### Invariants

1. `available == false` implies `reason != null`. A disabled engine with no reason is a contract violation, not a cosmetic issue.
2. `supported_accelerators == []` implies `available == true`. Unconstrained engines are always offered.
3. `warning` and `reason` are independent: an unavailable engine carries a reason, not a warning.
4. The endpoint never triggers a model download, never loads a model, and never imports torch at module scope — availability is computed from already-detected device state (Principle III, lazy heavy imports).
5. The response is stable within a process run for a given machine; it is not user-specific.
6. `warning` has two sources. A memory warning is produced only when the engine's default variant declares `min_memory_mb` and the detected memory is below it. A processor-fallback warning is produced when the detected accelerator is not declared but `"cpu"` is; the memory warning does not apply then (FR-023). Engines that declare no accelerators never warn.
7. Every field describes the **engine**, aggregated across its variants as stated above. Amended after the T010 code review on 2026-09-23.

---

## Principle V obligations

Adding this endpoint requires **all of the following in the same change**:

- [ ] Pydantic response models defined in `backend/models.py`.
- [ ] TypeScript client regenerated with `bun run generate:api`. The generated client (`app/src/lib/api/models/`, `services/` and `core/`) **must not** be hand-edited. `app/src/lib/api/types.ts` is a separate hand-written file and is edited normally.
- [ ] `GenerationRequest` gains two optional fields, both defaulting to `None` so every existing caller and agent integration is unaffected: `voice_description: str | None` (max 500 characters, matching `instruct`) and `advanced_settings: dict[str, float] | None`. A value outside a declared setting's bounds, or a name the engine does not declare, is rejected with a 422.
- [ ] `backend/README.md` updated to document the endpoint.
- [ ] New fields are additive and optional-by-default so existing agent integrations keep working untouched.

---

## Consumption rules for the app

- The engine picker reads `available`, `reason` and `warning` for `voxcpm` and renders it **greyed out with the reason** when unavailable, rather than hiding it (C1Q3, FR-003).
- The language selector reads `languages` for `voxcpm` instead of the hardcoded map (FR-007).
- Model management shows `size_mb` and asks for confirmation before starting the download when `requires_download_confirmation` is true (C1Q7, FR-018).
- The voice-description input is shown only when `supports_voice_design` is true, and its text is sent as `voice_description`, never as `instruct` (C1Q5, FR-015).
- Advanced controls are rendered from `advanced_settings`, prefilled with each `default`, and sent as `advanced_settings` (C1Q8, FR-010).
- **No `if (engine === 'voxcpm')` hardware or capability branching anywhere in `app/`.** That is the rule this contract exists to satisfy; a conditional on the *data* is fine, a conditional on the *name* is not.

---

## Closed item: the 30-language list

Closed by the dependency probe. The model card lists 30 codes, `ar` among them (FR-007):
zh, en, ar, my, da, nl, fi, fr, de, el, he, hi, id, it, ja, km, ko, lo, ms, no, pl, pt, ru,
es, sw, sv, tl, th, tr, vi. VoxCPM2 declares them in that order. Source:
evidence/probe/15-language-list.txt; the served list is in evidence/phase7/T042-registered.txt.
