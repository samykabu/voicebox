// T036 additions (supportsVoiceDesign, voiceDescriptionState, buildVoiceDescriptionPayload) are at the end of this file.
// T031/T032 additions (engineNotice, warning in downloadConfirmationDetails) are at the end of this file.
// T028 additions (supportsCloning, declaredCloningEngineOptions) are at the end of this file.
// Ad-hoc tests for the capability-driven frontend logic (T020, T022, T023).
// The app has no frontend test runner, so these run with bun's built-in runner from the
// session scratchpad and import the real app modules by absolute path.
import { describe, expect, test } from 'bun:test';
import {
  ENGINE_LANGUAGES,
  getLanguageOptionsForEngine,
} from 'D:/Projects/Personal/voicebox/app/src/lib/constants/languages';
import {
  advancedSettingStep,
  declaredCloningEngineOptions,
  downloadConfirmationDetails,
  engineNotice,
  buildAdvancedSettingsPayload,
  isEngineSelectable,
  needsDownloadConfirmation,
  supportsCloning,
  supportsVoiceDesign,
  voiceDescriptionState,
  buildVoiceDescriptionPayload,
} from 'D:/Projects/Personal/voicebox/app/src/lib/hooks/engineCapabilityRules';

// Mirrors the live GET /models/engines entry for voxcpm (backend/backends/__init__.py).
const VOXCPM_LANGS = [
  'zh', 'en', 'ar', 'my', 'da', 'nl', 'fi', 'fr', 'de', 'el', 'he', 'hi', 'id', 'it', 'ja',
  'km', 'ko', 'lo', 'ms', 'no', 'pl', 'pt', 'ru', 'es', 'sw', 'sv', 'tl', 'th', 'tr', 'vi',
];
const capability = (overrides: Record<string, unknown> = {}) =>
  ({
    engine: 'engine-under-test',
    display_name: 'Engine Under Test',
    available: true,
    reason: null,
    warning: null,
    supported_accelerators: ['cuda', 'mps', 'cpu'],
    detected_accelerator: 'cuda',
    languages: VOXCPM_LANGS,
    supports_cloning: false,
    supports_voice_design: true,
    requires_download_confirmation: true,
    advanced_settings: [
      { name: 'cfg_value', label: 'Guidance', default: 2.0, min: 1.0, max: 3.0 },
      { name: 'inference_timesteps', label: 'Quality steps', default: 10, min: 4, max: 30 },
    ],
    size_mb: 4961,
    license_id: 'Apache-2.0',
    commercial_use: true,
    ...overrides,
  }) as never;

describe('T020 getLanguageOptionsForEngine', () => {
  test('an engine without an app-side list uses its declared languages, in declared order', () => {
    const codes = getLanguageOptionsForEngine('engine-under-test', VOXCPM_LANGS).map((o) => o.value);
    expect(codes[0]).toBe('zh');
    expect(codes).toContain('ar');
    expect(codes).toHaveLength(30);
  });

  test('all 30 declared VoxCPM2 languages are offered, including the 7 added ones', () => {
    const codes = getLanguageOptionsForEngine('engine-under-test', VOXCPM_LANGS).map((o) => o.value);
    expect(codes).toEqual(VOXCPM_LANGS);
    for (const added of ['my', 'id', 'km', 'lo', 'tl', 'th', 'vi']) {
      expect(codes).toContain(added);
    }
  });

  test('declared codes the app cannot name are still filtered out', () => {
    const codes = getLanguageOptionsForEngine('engine-under-test', [...VOXCPM_LANGS, 'xx']).map(
      (o) => o.value,
    );
    expect(codes).not.toContain('xx');
    expect(codes).toHaveLength(30);
  });

  test('every option has a human label', () => {
    for (const opt of getLanguageOptionsForEngine('engine-under-test', VOXCPM_LANGS)) {
      expect(typeof opt.label).toBe('string');
      expect(opt.label.length).toBeGreaterThan(0);
    }
  });

  test('the eight unmigrated engines keep their hardcoded list even when a declaration is passed', () => {
    for (const engine of Object.keys(ENGINE_LANGUAGES)) {
      const withDeclared = getLanguageOptionsForEngine(engine, ['en']).map((o) => o.value);
      expect(withDeclared).toEqual([...ENGINE_LANGUAGES[engine]]);
    }
  });

  test('no declaration and no app-side list falls back to the previous default list', () => {
    const codes = getLanguageOptionsForEngine('engine-under-test').map((o) => o.value);
    expect(codes).toEqual([...ENGINE_LANGUAGES.qwen]);
    expect(getLanguageOptionsForEngine('engine-under-test', []).map((o) => o.value)).toEqual([
      ...ENGINE_LANGUAGES.qwen,
    ]);
  });
});

describe('T019 isEngineSelectable', () => {
  test('available engine is selectable; unavailable is not; unknown capability stays selectable', () => {
    expect(isEngineSelectable(capability())).toBe(true);
    expect(isEngineSelectable(capability({ available: false, reason: 'No GPU' }))).toBe(false);
    expect(isEngineSelectable(undefined)).toBe(true);
  });

  test('a warning never makes an engine unselectable', () => {
    expect(isEngineSelectable(capability({ warning: 'Low memory' }))).toBe(true);
  });
});

describe('T022 needsDownloadConfirmation', () => {
  test('confirmation is required when the capability says so and the model is not downloaded', () => {
    expect(needsDownloadConfirmation(capability(), { downloaded: false })).toBe(true);
  });

  test('no confirmation when the capability does not require it', () => {
    expect(
      needsDownloadConfirmation(capability({ requires_download_confirmation: false }), {
        downloaded: false,
      }),
    ).toBe(false);
    expect(needsDownloadConfirmation(undefined, { downloaded: false })).toBe(false);
  });

  test('no confirmation when the model is already downloaded or already downloading', () => {
    expect(needsDownloadConfirmation(capability(), { downloaded: true })).toBe(false);
    expect(needsDownloadConfirmation(capability(), { downloaded: false, downloading: true })).toBe(
      false,
    );
  });
});

describe('T023 buildAdvancedSettingsPayload', () => {
  test('sends every declared default when the user changed nothing', () => {
    expect(buildAdvancedSettingsPayload(capability(), undefined)).toEqual({
      cfg_value: 2.0,
      inference_timesteps: 10,
    });
  });

  test('sends user values, clamped to the declared bounds', () => {
    expect(
      buildAdvancedSettingsPayload(capability(), { cfg_value: 2.5, inference_timesteps: 99 }),
    ).toEqual({ cfg_value: 2.5, inference_timesteps: 30 });
    expect(buildAdvancedSettingsPayload(capability(), { cfg_value: 0 })).toEqual({
      cfg_value: 1.0,
      inference_timesteps: 10,
    });
  });

  test('drops names the engine does not declare', () => {
    expect(buildAdvancedSettingsPayload(capability(), { other_engine_knob: 7 })).toEqual({
      cfg_value: 2.0,
      inference_timesteps: 10,
    });
  });

  test('sends nothing for an engine that declares no settings, or with no capability', () => {
    expect(buildAdvancedSettingsPayload(capability({ advanced_settings: [] }), { cfg_value: 2 })).toBe(
      undefined,
    );
    expect(buildAdvancedSettingsPayload(undefined, { cfg_value: 2 })).toBe(undefined);
  });

  test('non-finite user values fall back to the default', () => {
    expect(buildAdvancedSettingsPayload(capability(), { cfg_value: Number.NaN })).toEqual({
      cfg_value: 2.0,
      inference_timesteps: 10,
    });
  });
});

describe('T023 advancedSettingStep', () => {
  test('integer declarations with a wide range step by 1; narrow or fractional ones by 0.1', () => {
    expect(advancedSettingStep({ name: 'n', label: 'n', default: 10, min: 4, max: 30 })).toBe(1);
    expect(advancedSettingStep({ name: 'c', label: 'c', default: 2.0, min: 1.0, max: 3.0 })).toBe(
      0.1,
    );
    expect(advancedSettingStep({ name: 'c', label: 'c', default: 2.5, min: 1.0, max: 30 })).toBe(
      0.1,
    );
  });
});

// ── T028: cloning profiles for engines that declare supports_cloning ─────────────────
// The app-side set mirrors the six older cloning engines listed in EngineModelSelector.tsx.
const APP_SIDE_CLONING = new Set(['qwen', 'luxtts', 'chatterbox', 'chatterbox_turbo', 'tada', 'f5_tts']);
const capsResponse = (...engines: unknown[]) => ({ engines }) as never;

describe('T028 supportsCloning', () => {
  test('an engine outside the app-side set clones only when its capability declares it', () => {
    expect(supportsCloning('engine-under-test', capability({ supports_cloning: true }), APP_SIDE_CLONING)).toBe(true);
    expect(supportsCloning('engine-under-test', capability({ supports_cloning: false }), APP_SIDE_CLONING)).toBe(false);
  });

  test('an unreported engine outside the app-side set does not clone', () => {
    expect(supportsCloning('engine-under-test', undefined, APP_SIDE_CLONING)).toBe(false);
  });

  test('app-side engines keep cloning with or without a capability (scope boundary)', () => {
    for (const engine of APP_SIDE_CLONING) {
      expect(supportsCloning(engine, undefined, APP_SIDE_CLONING)).toBe(true);
      expect(supportsCloning(engine, capability({ engine, supports_cloning: true }), APP_SIDE_CLONING)).toBe(true);
    }
  });

  test('the decision reads the capability, not the engine id', () => {
    // Same capability, different ids: same answer. Same id, different capability: different answer.
    const declared = capability({ supports_cloning: true });
    expect(supportsCloning('a', declared, APP_SIDE_CLONING)).toBe(supportsCloning('b', declared, APP_SIDE_CLONING));
    expect(supportsCloning('voxcpm', capability({ supports_cloning: false }), APP_SIDE_CLONING)).toBe(false);
    expect(supportsCloning('voxcpm', capability({ supports_cloning: true }), APP_SIDE_CLONING)).toBe(true);
  });
});

describe('T028 declaredCloningEngineOptions', () => {
  const listed = new Set(['qwen', 'kokoro']);

  test('adds reported engines that declare cloning and are not already listed, labelled by display_name', () => {
    const caps = capsResponse(
      capability({ engine: 'engine-under-test', display_name: 'Engine Under Test', supports_cloning: true }),
      capability({ engine: 'qwen', display_name: 'Qwen', supports_cloning: true }),
      capability({ engine: 'kokoro', display_name: 'Kokoro', supports_cloning: false }),
      capability({ engine: 'no-clone', display_name: 'No Clone', supports_cloning: false }),
    );
    expect(declaredCloningEngineOptions(caps, listed)).toEqual([
      { value: 'engine-under-test', label: 'Engine Under Test' },
    ]);
  });

  test('an engine this machine cannot run is still offered (FR-003 greys it out at generation time)', () => {
    const caps = capsResponse(capability({ engine: 'x', display_name: 'X', supports_cloning: true, available: false }));
    expect(declaredCloningEngineOptions(caps, listed)).toEqual([{ value: 'x', label: 'X' }]);
  });

  test('no capabilities (not loaded, or an older backend) adds nothing', () => {
    expect(declaredCloningEngineOptions(undefined, listed)).toEqual([]);
    expect(declaredCloningEngineOptions(capsResponse(), listed)).toEqual([]);
  });
});

// ── T031: an unavailable engine shows its reason; an available one shows its warning ──
const WARNING = 'This machine has about 4 GB of graphics memory. Engine Under Test usually needs about 8 GB, so generation may fail.';
const REASON = "Engine Under Test can't run on this machine: it needs CUDA, but this machine is using CPU.";

describe('T031 engineNotice', () => {
  test('an unavailable engine shows its reason, and stays listed as not selectable', () => {
    const cap = capability({ available: false, reason: REASON });
    expect(engineNotice(cap)).toEqual({ kind: 'reason', text: REASON });
    expect(isEngineSelectable(cap)).toBe(false);
  });

  test('an unavailable engine without a reason still explains itself, using its display name', () => {
    const notice = engineNotice(capability({ available: false, reason: null }));
    expect(notice?.kind).toBe('reason');
    expect(notice?.text).toContain('Engine Under Test');
  });

  test('an available engine shows its warning', () => {
    expect(engineNotice(capability({ warning: WARNING }))).toEqual({ kind: 'warning', text: WARNING });
  });

  test('a warning never blocks: the engine stays selectable (C1Q4)', () => {
    const cap = capability({ warning: WARNING });
    expect(isEngineSelectable(cap)).toBe(true);
    expect(engineNotice(cap)?.kind).toBe('warning');
  });

  test('nothing to show for a clean engine or an unreported one', () => {
    expect(engineNotice(capability())).toBe(null);
    expect(engineNotice(undefined)).toBe(null);
  });
});

// ── T032: the memory warning reaches the download confirmation, and never blocks it ──
describe('T032 downloadConfirmationDetails warning', () => {
  test('the capability warning is included in the confirmation details', () => {
    expect(downloadConfirmationDetails(capability({ warning: WARNING })).warning).toBe(WARNING);
  });

  test('no warning means none in the details', () => {
    expect(downloadConfirmationDetails(capability()).warning ?? null).toBe(null);
  });

  test('a warning never blocks the download: confirmation depends only on the declaration and model state', () => {
    const notDownloaded = { downloaded: false };
    expect(needsDownloadConfirmation(capability({ warning: WARNING }), notDownloaded)).toBe(
      needsDownloadConfirmation(capability(), notDownloaded),
    );
    expect(
      needsDownloadConfirmation(
        capability({ warning: WARNING, requires_download_confirmation: false }),
        notDownloaded,
      ),
    ).toBe(false);
    expect(needsDownloadConfirmation(capability({ warning: WARNING }), { downloaded: true })).toBe(false);
  });
});

// ── T036: the voice-description input (FR-015, C1Q5, C1Q6), decided by capability data only ──
describe('T036 supportsVoiceDesign', () => {
  test('true only when the capability declares supports_voice_design', () => {
    expect(supportsVoiceDesign(capability())).toBe(true);
    expect(supportsVoiceDesign(capability({ supports_voice_design: false }))).toBe(false);
    expect(supportsVoiceDesign(undefined)).toBe(false);
  });
});

describe('T036 voiceDescriptionState', () => {
  const designer = capability({ supports_voice_design: true });
  const plain = capability({ supports_voice_design: false });

  test('hidden when the engine does not support voice design, whatever the profile', () => {
    expect(voiceDescriptionState(plain, { voice_type: 'preset' })).toBe('hidden');
    expect(voiceDescriptionState(plain, { voice_type: 'cloned' })).toBe('hidden');
    expect(voiceDescriptionState(plain, undefined)).toBe('hidden');
    expect(voiceDescriptionState(undefined, { voice_type: 'designed' })).toBe('hidden');
  });

  test('unused when the selected profile has reference audio: the recording wins (C1Q6)', () => {
    expect(voiceDescriptionState(designer, { voice_type: 'cloned' })).toBe('unused');
    // A profile with no voice_type is a legacy cloned profile.
    expect(voiceDescriptionState(designer, {})).toBe('unused');
  });

  test('active for a profile without reference audio, or no profile', () => {
    expect(voiceDescriptionState(designer, { voice_type: 'designed' })).toBe('active');
    expect(voiceDescriptionState(designer, { voice_type: 'preset' })).toBe('active');
    expect(voiceDescriptionState(designer, undefined)).toBe('active');
  });

  test('no engine name decides the result: any engine declaring voice design is active', () => {
    const kokoroDesigner = capability({ engine: 'kokoro', supports_voice_design: true });
    expect(voiceDescriptionState(kokoroDesigner, { voice_type: 'preset' })).toBe('active');
    const voxcpmWithout = capability({ engine: 'voxcpm', supports_voice_design: false });
    expect(voiceDescriptionState(voxcpmWithout, { voice_type: 'preset' })).toBe('hidden');
  });
});

describe('T036 buildVoiceDescriptionPayload', () => {
  const designer = capability({ supports_voice_design: true });
  const TEXT = 'A calm older woman with a low, warm voice';

  test('omitted for engines without voice design, so their requests are unchanged', () => {
    expect(
      buildVoiceDescriptionPayload(capability({ supports_voice_design: false }), undefined, TEXT),
    ).toBeUndefined();
    expect(buildVoiceDescriptionPayload(undefined, undefined, TEXT)).toBeUndefined();
  });

  test('omitted when the description is unused because the profile has a recording', () => {
    expect(buildVoiceDescriptionPayload(designer, { voice_type: 'cloned' }, TEXT)).toBeUndefined();
  });

  test('the trimmed text when active', () => {
    expect(buildVoiceDescriptionPayload(designer, { voice_type: 'preset' }, `  ${TEXT}\n`)).toBe(TEXT);
    expect(buildVoiceDescriptionPayload(designer, undefined, TEXT)).toBe(TEXT);
  });

  test('any language is sent as written (C1Q9)', () => {
    const arabic = 'صوت امرأة هادئ ودافئ';
    expect(buildVoiceDescriptionPayload(designer, { voice_type: 'designed' }, arabic)).toBe(arabic);
  });

  test('blank or missing text is undefined', () => {
    expect(buildVoiceDescriptionPayload(designer, undefined, '   ')).toBeUndefined();
    expect(buildVoiceDescriptionPayload(designer, undefined, '')).toBeUndefined();
    expect(buildVoiceDescriptionPayload(designer, undefined, undefined)).toBeUndefined();
  });

  test('no engine name decides the result', () => {
    const kokoroDesigner = capability({ engine: 'kokoro', supports_voice_design: true });
    expect(buildVoiceDescriptionPayload(kokoroDesigner, undefined, TEXT)).toBe(TEXT);
  });
});
