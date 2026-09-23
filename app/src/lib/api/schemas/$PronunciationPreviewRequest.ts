/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationPreviewRequest = {
    description: `Request to see what the dictionary would do to a piece of text.`,
    properties: {
        text: {
            type: 'string',
            isRequired: true,
            maxLength: 50000,
            minLength: 1,
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
    },
} as const;
