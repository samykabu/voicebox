/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Delete selected generations or every inactive history entry.
 */
export type HistoryBulkDeleteRequest = {
    generation_ids?: Array<string>;
    delete_all?: boolean;
    excluded_ids?: Array<string>;
};

