/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationPreviewResponse = {
    description: `What the engine would actually be given, and why it differs.`,
    properties: {
        original: {
            type: 'string',
            isRequired: true,
        },
        result: {
            type: 'string',
            isRequired: true,
        },
        applied: {
            type: 'array',
            contains: {
                type: 'PronunciationSubstitution',
            },
            isRequired: true,
        },
    },
} as const;
