T012 (issue #28): document GET /models/engines in backend/README.md (Principle V, FR-024)
Timestamp: 2026-09-23T02:40:06Z
Branch: feature/001-voxcpm2-tts-engine

Source of truth: specs/001-voxcpm2-tts-engine/contracts/engine-capabilities.md (post-T010 behaviour).

Tests: none apply. This is a documentation-only change to backend/README.md; no code changed.

Endpoint count: the README says '90 endpoints'. Left unchanged.
Command: grep -rh '@router\.' backend/routes/ | wc -l  ->  129
This differs a lot from 90, and the method behind the original 90 is unknown, so the number was not changed.

=== git diff backend/README.md ===
diff --git a/backend/README.md b/backend/README.md
index 170cab1..e753c6e 100644
--- a/backend/README.md
+++ b/backend/README.md
@@ -88,7 +88,7 @@ Detection is handled by `utils/platform_detect.py`. Both backends implement the
 | Stories | `/stories` | Multi-track timeline editor, audio export |
 | Effects | `/effects` | Effect presets, preview, version management |
 | Audio | `/audio`, `/samples` | Audio file serving |
-| Models | `/models` | Load, unload, download, migrate, status |
+| Models | `/models` | Load, unload, download, migrate, status, engine capabilities |
 | Tasks | `/tasks`, `/cache` | Active task tracking, cache management |
 | CUDA | `/backend/cuda-*` | CUDA binary download and management |
 
@@ -107,6 +107,56 @@ curl http://localhost:17493/profiles
 curl http://localhost:17493/generate/{id}/status
 ```
 
+### Engine capabilities
+
+`GET /models/engines` is read-only and takes no parameters. It returns one entry per TTS engine in `TTS_ENGINES`, so the app can learn what an engine supports and whether it can run on this machine. It never loads a model, never starts a download and never imports torch at module scope.
+
+```bash
+curl http://localhost:17493/models/engines
+```
+
+```json
+{
+  "engines": [
+    {
+      "engine": "kokoro",
+      "display_name": "Kokoro",
+      "available": true,
+      "reason": null,
+      "warning": null,
+      "supported_accelerators": [],
+      "detected_accelerator": "cuda",
+      "languages": ["en", "es", "fr", "hi", "it", "pt", "ja", "zh"],
+      "supports_cloning": false,
+      "supports_voice_design": false,
+      "requires_download_confirmation": false,
+      "advanced_settings": [],
+      "size_mb": 350,
+      "license_id": null,
+      "commercial_use": null
+    }
+  ]
+}
+```
+
+Each entry describes the engine across all of its model variants:
+
+- `display_name` is the engine name from `TTS_ENGINES` (for example "TADA" or "F5-TTS"), not a variant name.
+- `languages` is the union of every variant's languages.
+- `license_id` and `commercial_use` hold the shared value when every variant agrees, and `null` when they differ.
+- `size_mb`, `supports_voice_design`, `requires_download_confirmation`, `advanced_settings` and `supported_accelerators` come from the default-size variant, the one downloaded by default.
+- `supports_cloning` comes from `CLONING_ENGINES`.
+- `detected_accelerator` is the accelerator detected on this machine.
+- `reason` is non-null if and only if `available` is false. An empty `supported_accelerators` list means unconstrained, and such an engine is always available.
+- `warning` is advisory. It appears when detected memory is below the engine's usual need (`min_memory_mb`) and never blocks generation.
+
+`POST /generate` accepts two optional fields, both defaulting to `null`, so existing callers are unaffected:
+
+- `voice_description`: up to 500 characters, for engines with `supports_voice_design`. It is never sent as `instruct`.
+- `advanced_settings`: an object mapping a setting name to a number. Only names the engine declares in `advanced_settings` are allowed, within their `min`/`max`. Anything else returns 422.
+
+See [contracts/engine-capabilities.md](../specs/001-voxcpm2-tts-engine/contracts/engine-capabilities.md) for the full field contract.
+
 ## Data directory
 
 ```
