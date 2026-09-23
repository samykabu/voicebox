import type { EngineAdvancedSettingResponse } from '@/lib/api/models/EngineAdvancedSettingResponse';
import type { EngineCapabilityResponse } from '@/lib/api/models/EngineCapabilityResponse';

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

/** What a download confirmation shows, filled from the engine's capability declaration. */
export interface DownloadConfirmationDetails {
  displayName: string;
  sizeMb: number;
  licenseId?: string | null;
  commercialUse?: boolean | null;
}

/** Confirmation details for an engine's default download (FR-018: size, FR-005: licence). */
export function downloadConfirmationDetails(
  capability: EngineCapabilityResponse,
  displayName?: string,
): DownloadConfirmationDetails {
  return {
    displayName: displayName || capability.display_name,
    sizeMb: capability.size_mb,
    licenseId: capability.license_id,
    commercialUse: capability.commercial_use,
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
