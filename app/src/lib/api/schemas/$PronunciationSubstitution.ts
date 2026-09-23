/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PronunciationSubstitution = {
    description: `One replacement the dictionary made.`,
    properties: {
        term: {
            type: 'string',
            isRequired: true,
        },
        replacement: {
            type: 'string',
            isRequired: true,
        },
        entry_id: {
            type: 'string',
            isRequired: true,
        },
    },
} as const;
