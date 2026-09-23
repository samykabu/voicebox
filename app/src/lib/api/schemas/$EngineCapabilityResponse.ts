/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EngineCapabilityResponse = {
    description: `One TTS engine's capabilities and whether this machine can run it (FR-004).
    Describes the engine as a whole, aggregated from all of its model variants.
    See specs/001-voxcpm2-tts-engine/contracts/engine-capabilities.md.`,
    properties: {
        engine: {
            type: 'string',
            isRequired: true,
        },
        display_name: {
            type: 'string',
            description: `The engine name (not a model variant name).`,
            isRequired: true,
        },
        available: {
            type: 'boolean',
            isRequired: true,
        },
        reason: {
            type: 'any-of',
            description: `Non-null if and only if available is false.`,
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
        warning: {
            type: 'any-of',
            description: `Advisory only; never blocks.`,
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
        supported_accelerators: {
            type: 'array',
            contains: {
                type: 'string',
            },
            isRequired: true,
        },
        detected_accelerator: {
            type: 'string',
            isRequired: true,
        },
        languages: {
            type: 'array',
            contains: {
                type: 'string',
            },
            isRequired: true,
        },
        supports_cloning: {
            type: 'boolean',
            isRequired: true,
        },
        supports_voice_design: {
            type: 'boolean',
            description: `From the default-size variant.`,
            isRequired: true,
        },
        requires_download_confirmation: {
            type: 'boolean',
            description: `From the default-size variant.`,
            isRequired: true,
        },
        advanced_settings: {
            type: 'array',
            contains: {
                type: 'EngineAdvancedSettingResponse',
            },
            isRequired: true,
        },
        size_mb: {
            type: 'number',
            description: `Download size of the default-size variant, the one downloaded by default.`,
            isRequired: true,
        },
        license_id: {
            type: 'any-of',
            description: `Shared by every variant, or null when the variants differ.`,
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
        commercial_use: {
            type: 'any-of',
            description: `Shared by every variant, or null when the variants differ.`,
            contains: [{
                type: 'boolean',
            }, {
                type: 'null',
            }],
            isRequired: true,
        },
    },
} as const;
