/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationEntryUpdate = {
    description: `Request model for updating a pronunciation entry. Omitted fields are left alone.`,
    properties: {
        term: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 200,
                minLength: 1,
            }, {
                type: 'null',
            }],
        },
        replacement: {
            type: 'any-of',
            contains: [{
                type: 'string',
                maxLength: 500,
                minLength: 1,
            }, {
                type: 'null',
            }],
        },
        language: {
            type: 'any-of',
            contains: [{
                type: 'string',
                pattern: '^(zh|en|ja|ko|de|fr|ru|pt|es|it|he|ar|da|el|fi|hi|ms|nl|no|pl|sv|sw|tr)$',
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
            type: 'any-of',
            contains: [{
                type: 'boolean',
            }, {
                type: 'null',
            }],
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
