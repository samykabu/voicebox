/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response model for a pronunciation entry.
 */
export type PronunciationEntryResponse = {
    id: string;
    term: string;
    replacement: string;
    language?: (string | null);
    profile_id?: (string | null);
    enabled?: boolean;
    notes?: (string | null);
    created_at: string;
    updated_at: string;
};

