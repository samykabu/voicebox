/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EngineAdvancedSettingResponse } from './EngineAdvancedSettingResponse';
/**
 * One TTS engine's capabilities and whether this machine can run it (FR-004).
 *
 * Describes the engine as a whole, aggregated from all of its model variants.
 * See specs/001-voxcpm2-tts-engine/contracts/engine-capabilities.md.
 */
export type EngineCapabilityResponse = {
    engine: string;
    /**
     * The engine name (not a model variant name).
     */
    display_name: string;
    available: boolean;
    /**
     * Non-null if and only if available is false.
     */
    reason: (string | null);
    /**
     * Advisory only; never blocks.
     */
    warning: (string | null);
    /**
     * From the default-size variant. Empty means unconstrained.
     */
    supported_accelerators: Array<string>;
    detected_accelerator: string;
    /**
     * Union across all of the engine's variants, in first-seen order over the variants in registry order.
     */
    languages: Array<string>;
    supports_cloning: boolean;
    /**
     * From the default-size variant.
     */
    supports_voice_design: boolean;
    /**
     * From the default-size variant.
     */
    requires_download_confirmation: boolean;
    /**
     * From the default-size variant.
     */
    advanced_settings: Array<EngineAdvancedSettingResponse>;
    /**
     * Download size of the default-size variant, the one downloaded by default.
     */
    size_mb: number;
    /**
     * Shared by every variant, or null when the variants differ.
     */
    license_id: (string | null);
    /**
     * Shared by every variant, or null when the variants differ.
     */
    commercial_use: (boolean | null);
};

