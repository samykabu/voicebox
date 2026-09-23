/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $HistoryBulkDeleteRequest = {
    description: `Delete selected generations or every inactive history entry.`,
    properties: {
        generation_ids: {
            type: 'array',
            contains: {
                type: 'string',
            },
        },
        delete_all: {
            type: 'boolean',
        },
        excluded_ids: {
            type: 'array',
            contains: {
                type: 'string',
            },
        },
    },
} as const;
