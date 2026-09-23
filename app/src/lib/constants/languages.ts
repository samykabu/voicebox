/**
 * Supported languages for voice generation, per engine.
 *
 * Qwen3-TTS supports 10 languages.
 * LuxTTS is English-only.
 * Chatterbox Multilingual supports 23 languages.
 * Chatterbox Turbo is English-only.
 * Kokoro supports 8 languages.
 */

/** All languages that any engine supports. */
export const ALL_LANGUAGES = {
  ar: 'Arabic',
  da: 'Danish',
  de: 'German',
  el: 'Greek',
  en: 'English',
  es: 'Spanish',
  fi: 'Finnish',
  fr: 'French',
  he: 'Hebrew',
  hi: 'Hindi',
  it: 'Italian',
  ja: 'Japanese',
  ko: 'Korean',
  ms: 'Malay',
  nl: 'Dutch',
  no: 'Norwegian',
  pl: 'Polish',
  pt: 'Portuguese',
  ru: 'Russian',
  sv: 'Swedish',
  sw: 'Swahili',
  tr: 'Turkish',
  zh: 'Chinese',
} as const;

export type LanguageCode = keyof typeof ALL_LANGUAGES;

/** Per-engine supported language codes. */
export const ENGINE_LANGUAGES: Record<string, readonly LanguageCode[]> = {
  qwen: ['zh', 'en', 'ja', 'ko', 'de', 'fr', 'ru', 'pt', 'es', 'it'],
  luxtts: ['en'],
  chatterbox: [
    'ar',
    'da',
    'de',
    'el',
    'en',
    'es',
    'fi',
    'fr',
    'he',
    'hi',
    'it',
    'ja',
    'ko',
    'ms',
    'nl',
    'no',
    'pl',
    'pt',
    'ru',
    'sv',
    'sw',
    'tr',
    'zh',
  ],
  chatterbox_turbo: ['en'],
  tada: ['en', 'ar', 'zh', 'de', 'es', 'fr', 'it', 'ja', 'pl', 'pt'],
  kokoro: ['en', 'es', 'fr', 'hi', 'it', 'pt', 'ja', 'zh'],
  qwen_custom_voice: ['zh', 'en', 'ja', 'ko', 'de', 'fr', 'ru', 'pt', 'es', 'it'],
  f5_tts: ['ar'],
} as const;

function isLanguageCode(code: string): code is LanguageCode {
  return (Object.keys(ALL_LANGUAGES) as string[]).includes(code);
}

/**
 * Helper: get language options for a given engine.
 *
 * `declaredLanguages` is the engine's `languages` from `useEngineCapabilities` (FR-007,
 * FR-024). It is used for any engine without an app-side list above; the engines listed in
 * `ENGINE_LANGUAGES` are not migrated to the capability channel yet and keep their list
 * (contracts/engine-capabilities.md, "Scope boundary"). Declared codes missing from
 * `ALL_LANGUAGES` are dropped: the app has no name for them and the backend's
 * `GenerationRequest.language` pattern would reject them.
 */
export function getLanguageOptionsForEngine(engine: string, declaredLanguages?: readonly string[]) {
  const declared = declaredLanguages?.filter(isLanguageCode) ?? [];
  const codes =
    ENGINE_LANGUAGES[engine] ?? (declared.length > 0 ? declared : ENGINE_LANGUAGES.qwen);
  return codes.map((code) => ({
    value: code,
    label: ALL_LANGUAGES[code],
  }));
}

// ── Backwards-compatible exports used elsewhere ──────────────────────
export const SUPPORTED_LANGUAGES = ALL_LANGUAGES;
export const LANGUAGE_CODES = Object.keys(ALL_LANGUAGES) as LanguageCode[];
export const LANGUAGE_OPTIONS = LANGUAGE_CODES.map((code) => ({
  value: code,
  label: ALL_LANGUAGES[code],
}));
