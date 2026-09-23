/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EngineAdvancedSettingResponse = {
    description: `An advanced generation setting an engine declares (FR-010).`,
    properties: {
        name: {
            type: 'string',
            isRequired: true,
        },
        label: {
            type: 'string',
            isRequired: true,
        },
        default: {
            type: 'number',
            isRequired: true,
        },
        min: {
            type: 'number',
            isRequired: true,
        },
        max: {
            type: 'number',
            isRequired: true,
        },
    },
} as const;
