/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationEntryCreate = {
    description: `Request model for creating a pronunciation entry.`,
    properties: {
        term: {
            type: 'string',
            isRequired: true,
            maxLength: 200,
            minLength: 1,
        },
        replacement: {
            type: 'string',
            isRequired: true,
            maxLength: 500,
            minLength: 1,
        },
        language: {
            type: 'any-of',
            description: `Apply only when generating in this language. Omit for all languages.`,
            contains: [{
                type: 'string',
                pattern: '^(zh|en|ja|ko|de|fr|ru|pt|es|it|he|ar|da|el|fi|hi|ms|nl|no|pl|sv|sw|tr)$',
            }, {
                type: 'null',
            }],
        },
        profile_id: {
            type: 'any-of',
            description: `Scope to one voice. Omit for a global entry.`,
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
                maxLength: 1000,
            }, {
                type: 'null',
            }],
        },
    },
} as const;
