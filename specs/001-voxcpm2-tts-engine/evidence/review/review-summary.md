# Review: VoxCPM2 feature (2026-09-23)

Two read-only reviewers checked `git diff main...HEAD`: one for `backend/`, one for the app, build, release files and docs. Each finding needed confidence of 80 or more.

## Round 1 (at 90913de)

| ID | Area | Finding | Fixed in |
| --- | --- | --- | --- |
| I1 | backend | VoxCPM2 declared `retries_runaway=True`, adding Voicebox's own split-and-retry on top of the vendor's (contract rule 4) | 20c4224 |
| I2 | backend | No load or inference lock; concurrent stream and queued loads could load the model twice | 20c4224 |
| I3 | backend | Designed long text sampled a new speaker per chunk | 20c4224 (chunk 0 cloned for later chunks) |
| I4 | backend | Retry and regenerate dropped the one-off voice description | 20c4224 (nullable `generations.voice_description`) |
| S1-S3 | backend | Null-engine advanced-settings check; section banner; f-string log | 20c4224 |
| F1 | app | Cold start switched a VoxCPM2 profile off its engine before capabilities loaded | 55ef593 |
| F2 | app | Download confirmation failed open when capabilities were missing | 55ef593 |
| F3 | app | New strings bypassed i18n | 55ef593 |
| F4-F5 | app | Describe-a-voice draft lost; picker gave no reason | 55ef593 |

Docs for these: ec1dbc3.

## Round 2 (re-review of the fixes)

- Backend, 90913de..ec1dbc3: all fixed, Blocking: 0. Suggestion S4 (continuation WAV leaked on cancel) fixed in 55cf236, with Q3 (generation export carries `voice_description`).
- App, 90913de..ec1dbc3: all fixed, Blocking: 0.
- Backend, ec1dbc3..55cf236: Blocking: 0. Suggestion S5 (import dropped engine and model size) fixed in b0b7ad3.
- Backend, 55cf236..b0b7ad3: Blocking: 0. Suggestion S6 (imported voice description and other fields unvalidated) fixed in 68e9cc0.
- 68e9cc0 checked by the dispatcher: the description gets the API's rules (string, stripped, at most 500 characters, voice-design engine only), other fields get type checks with safe fallbacks, blank text rejects the import before any file is copied, and a failed commit removes the copied audio. 34 new tests; full suite in evidence/verify.

Test evidence for each fix (red then green, JUnit XML) is in this folder. The real designed long-text run is in I3-realrun.txt; the human listening check of that file is recorded separately when the user confirms it.

## Open, not blocking

- `instruct` on import is not length-limited and `language` is not pattern-checked; both predate this feature.

Blocking findings: 0.
