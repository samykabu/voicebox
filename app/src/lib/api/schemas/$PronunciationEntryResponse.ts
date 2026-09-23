/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationEntryResponse = {
    description: `Response model for a pronunciation entry.`,
    properties: {
        id: {
            type: 'string',
            isRequired: true,
        },
        term: {
            type: 'string',
            isRequired: true,
        },
        replacement: {
            type: 'string',
            isRequired: true,
        },
        language: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        profile_id: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        enabled: {
            type: 'boolean',
        },
        notes: {
            type: 'any-of',
            contains: [{
                type: 'string',
            }, {
                type: 'null',
            }],
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
        updated_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
