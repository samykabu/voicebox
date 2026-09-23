import type { EngineAdvancedSettingResponse } from '@/lib/api/models/EngineAdvancedSettingResponse';
import type { EngineCapabilitiesResponse } from '@/lib/api/models/EngineCapabilitiesResponse';
import type { EngineCapabilityResponse } from '@/lib/api/models/EngineCapabilityResponse';
import { ENGINE_LANGUAGES } from '@/lib/constants/languages';

/**
 * Pure decisions the UI derives from an engine's declared capabilities
 * (contracts/engine-capabilities.md, "Consumption rules for the app").
 *
 * Each rule reads capability data only, never an engine name (FR-004). An engine the
 * backend does not report (capability `undefined`) keeps today's behaviour.
 */

/** An engine can be picked unless the backend says this machine cannot run it (FR-003). */
export function isEngineSelectable(capability: EngineCapabilityResponse | undefined): boolean {
  return capability ? capability.available : true;
}

/**
 * The UI's translate function (i18next's `t`), passed in so these rules stay free of hooks.
 */
export type TranslateFn = (key: string, params?: Record<string, string>) => string;

/** An i18n key and its interpolation values, for callers that translate later. */
export interface TranslatableMessage {
  key: string;
  params: Record<string, string>;
}

/**
 * The message for an unavailable engine whose capability gives no `reason`: the
 * `engines.cannotRunHere` key, filled with the engine's declared display name.
 */
export function engineUnavailableFallback(
  capability: EngineCapabilityResponse,
): TranslatableMessage {
  return { key: 'engines.cannotRunHere', params: { name: capability.display_name } };
}

/** A line shown next to an engine: why it cannot run, or an advisory warning. */
export interface EngineNotice {
  kind: 'reason' | 'warning';
  text: string;
}

/**
 * What to show next to an engine (FR-003, C1Q3, C1Q4). An unavailable engine shows its
 * `reason`, falling back to a translated sentence built from its display name
 * (`engineUnavailableFallback`) so a greyed-out engine always explains itself; an available
 * engine shows its `warning`. A warning is advisory
 * only: it never changes `isEngineSelectable`.
 */
export function engineNotice(
  capability: EngineCapabilityResponse | undefined,
  t: TranslateFn,
): EngineNotice | null {
  if (!capability) return null;
  if (!capability.available) {
    if (capability.reason) return { kind: 'reason', text: capability.reason };
    const fallback = engineUnavailableFallback(capability);
    return { kind: 'reason', text: t(fallback.key, fallback.params) };
  }
  return capability.warning ? { kind: 'warning', text: capability.warning } : null;
}

/**
 * Whether a cloned (reference-audio) profile can be used with this engine (FR-011, FR-014).
 *
 * Engines in `appSideCloningEngines` are not migrated to the capability channel yet and keep
 * cloning whether or not the backend reports them (the same scope boundary as languages);
 * any other engine clones only when its capability declares `supports_cloning`.
 */
export function supportsCloning(
  engine: string,
  capability: EngineCapabilityResponse | undefined,
  appSideCloningEngines: ReadonlySet<string>,
): boolean {
  return appSideCloningEngines.has(engine) || capability?.supports_cloning === true;
}

/**
 * Cloning-capable engines the backend reports that an app-side option list does not name,
 * as options labelled with each engine's declared `display_name`. An unavailable engine is
 * still offered: availability is shown when generating (FR-003), not hidden here.
 */
export function declaredCloningEngineOptions(
  capabilities: EngineCapabilitiesResponse | undefined,
  listedEngines: ReadonlySet<string>,
): { value: string; label: string }[] {
  return (capabilities?.engines ?? [])
    .filter((entry) => entry.supports_cloning && !listedEngines.has(entry.engine))
    .map((entry) => ({ value: entry.engine, label: entry.display_name }));
}

/**
 * Whether starting this engine's model download must be confirmed first (FR-018, C1Q7).
 * A model that is already downloaded, or already downloading, needs no confirmation.
 */
export function needsDownloadConfirmation(
  capability: EngineCapabilityResponse | undefined,
  model: { downloaded: boolean; downloading?: boolean } | undefined,
): boolean {
  if (!capability?.requires_download_confirmation || !model) return false;
  return !model.downloaded && !model.downloading;
}

/**
 * Engines that predate the capability channel: the ones with an app-side language list
 * (contracts/engine-capabilities.md, "Scope boundary"). Without a capability they keep
 * today's behaviour; every other engine depends on its capability.
 */
export const PRE_CAPABILITY_ENGINES: ReadonlySet<string> = new Set(Object.keys(ENGINE_LANGUAGES));

/** What to do before a model download may start (FR-018). */
export type DownloadDecision = 'confirm' | 'proceed' | 'refuse';

/**
 * Whether a download may start, must be confirmed first, or must be refused (FR-018, C1Q7).
 *
 * It fails closed: when an engine outside `preCapabilityEngines` has no capability (for
 * example GET /models/engines could not be loaded), the app cannot know whether the download
 * needs confirmation, so it is refused unless the model is already downloaded or downloading.
 * A capability that requires confirmation is also asked for when the model's state is unknown.
 * A model with no engine (`engine` undefined, for example a transcription model) and a
 * pre-capability engine without a capability keep today's behaviour and proceed.
 */
export function downloadDecision(
  engine: string | undefined,
  capability: EngineCapabilityResponse | undefined,
  model: { downloaded: boolean; downloading?: boolean } | undefined,
  preCapabilityEngines: ReadonlySet<string>,
): DownloadDecision {
  const noDownload = !!model && (model.downloaded || !!model.downloading);
  if (noDownload) return 'proceed';
  if (!capability) {
    return !engine || preCapabilityEngines.has(engine) ? 'proceed' : 'refuse';
  }
  if (!capability.requires_download_confirmation) return 'proceed';
  return 'confirm';
}

/**
 * Whether the generate box should switch away from the selected engine because the selected
 * profile cannot use it.
 *
 * Until the capability list has loaded, only engines in `appSideEngines` are judged: their
 * compatibility is known app-side. Any other engine's compatibility comes from its capability,
 * so switching it away on a cold start would drop a valid choice.
 */
export function shouldFallBackFromEngine(args: {
  engine: string;
  currentEngineAvailable: boolean;
  optionCount: number;
  capabilitiesLoaded: boolean;
  appSideEngines: ReadonlySet<string>;
}): boolean {
  if (args.currentEngineAvailable || args.optionCount === 0) return false;
  return args.capabilitiesLoaded || args.appSideEngines.has(args.engine);
}

/** What a download confirmation shows, filled from the engine's capability declaration. */
export interface DownloadConfirmationDetails {
  displayName: string;
  sizeMb: number;
  licenseId?: string | null;
  commercialUse?: boolean | null;
  /** Advisory only, for example too little memory (C1Q4). Never blocks the download. */
  warning?: string | null;
}

/**
 * Confirmation details for an engine's default download (FR-018: size, FR-005: licence,
 * C1Q4: advisory warning).
 */
export function downloadConfirmationDetails(
  capability: EngineCapabilityResponse,
  displayName?: string,
): DownloadConfirmationDetails {
  return {
    displayName: displayName || capability.display_name,
    sizeMb: capability.size_mb,
    licenseId: capability.license_id,
    commercialUse: capability.commercial_use,
    warning: capability.warning,
  };
}

function clamp(value: number, setting: EngineAdvancedSettingResponse): number {
  return Math.min(setting.max, Math.max(setting.min, value));
}

/**
 * The request's `advanced_settings` for the selected engine (FR-010, C1Q8).
 *
 * Only settings the engine declares are sent, each clamped to its declared bounds and
 * falling back to its declared default. Engines that declare none get `undefined`, so the
 * field is omitted and existing engines' requests are unchanged.
 */
export function buildAdvancedSettingsPayload(
  capability: EngineCapabilityResponse | undefined,
  values: Record<string, number> | undefined,
): Record<string, number> | undefined {
  const declared = capability?.advanced_settings ?? [];
  if (declared.length === 0) return undefined;
  const payload: Record<string, number> = {};
  for (const setting of declared) {
    const chosen = values?.[setting.name];
    payload[setting.name] = clamp(
      typeof chosen === 'number' && Number.isFinite(chosen) ? chosen : setting.default,
      setting,
    );
  }
  return payload;
}

/**
 * Slider step for a declared setting. The declaration carries no type or step, so an
 * all-integer setting with a wide range (for example a step count) moves in whole numbers
 * and anything else in tenths.
 */
export function advancedSettingStep(setting: EngineAdvancedSettingResponse): number {
  const integral = [setting.default, setting.min, setting.max].every(Number.isInteger);
  return integral && setting.max - setting.min >= 10 ? 1 : 0.1;
}

/** Whether the engine can create a voice from a written description (FR-015). */
export function supportsVoiceDesign(capability: EngineCapabilityResponse | undefined): boolean {
  return capability?.supports_voice_design === true;
}

/**
 * The voice description's state for the selected engine and profile (FR-015, C1Q5, C1Q6).
 *
 * - `hidden`: the engine does not declare voice design, so the input is not shown.
 * - `unused`: the profile has reference audio (a cloned profile; a profile with no
 *   `voice_type` is a legacy cloned one). The recording wins and the UI says so.
 * - `active`: the description is sent as `voice_description`.
 */
export type VoiceDescriptionState = 'hidden' | 'unused' | 'active';

export function voiceDescriptionState(
  capability: EngineCapabilityResponse | undefined,
  profile: { voice_type?: string | null } | undefined,
): VoiceDescriptionState {
  if (!supportsVoiceDesign(capability)) return 'hidden';
  if (profile && (!profile.voice_type || profile.voice_type === 'cloned')) return 'unused';
  return 'active';
}

/**
 * The request's `voice_description`: the trimmed text when the description is active and not
 * blank, otherwise `undefined`, so the field is omitted and existing engines' requests are
 * unchanged. It is never sent as `instruct` (C1Q5).
 */
export function buildVoiceDescriptionPayload(
  capability: EngineCapabilityResponse | undefined,
  profile: { voice_type?: string | null } | undefined,
  text: string | undefined,
): string | undefined {
  if (voiceDescriptionState(capability, profile) !== 'active') return undefined;
  const trimmed = text?.trim();
  return trimmed ? trimmed : undefined;
}

/** An engine offered for the "Describe a voice" profile source (FR-015a). */
export interface VoiceDesignEngineOption {
  value: string;
  label: string;
  available: boolean;
}

/**
 * Engines whose capability declares `supports_voice_design`, labelled with each engine's
 * declared `display_name` (FR-015a). An unavailable engine is still listed, marked as such,
 * so availability is shown rather than hidden (FR-003).
 */
export function voiceDesignEngineOptions(
  capabilities: EngineCapabilitiesResponse | undefined,
): VoiceDesignEngineOption[] {
  return (capabilities?.engines ?? [])
    .filter((entry) => supportsVoiceDesign(entry))
    .map((entry) => ({
      value: entry.engine,
      label: entry.display_name,
      available: entry.available,
    }));
}

/**
 * The engine a designed profile is created for: the current choice when it is a voice-design
 * engine, otherwise the first available one, otherwise the first declared one ('' if none).
 */
export function pickVoiceDesignEngine(
  options: readonly VoiceDesignEngineOption[],
  current?: string,
): string {
  if (current && options.some((option) => option.value === current)) return current;
  return (options.find((option) => option.available) ?? options[0])?.value ?? '';
}

/** Matches `design_prompt` in the backend's VoiceProfileCreate (max_length=2000). */
export const MAX_DESIGN_PROMPT_CHARS = 2000;

/** Validation for a designed profile's description: required, and within the backend limit. */
export function designPromptError(text: string | undefined): 'required' | 'tooLong' | null {
  if (!text?.trim()) return 'required';
  if (text.length > MAX_DESIGN_PROMPT_CHARS) return 'tooLong';
  return null;
}
