/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EngineCapabilitiesResponse = {
    description: `Response model for GET /models/engines.`,
    properties: {
        engines: {
            type: 'array',
            contains: {
                type: 'EngineCapabilityResponse',
            },
            isRequired: true,
        },
    },
} as const;
