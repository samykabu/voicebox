/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request model for creating a pronunciation entry.
 */
export type PronunciationEntryCreate = {
    term: string;
    replacement: string;
    /**
     * Apply only when generating in this language. Omit for all languages.
     */
    language?: (string | null);
    /**
     * Scope to one voice. Omit for a global entry.
     */
    profile_id?: (string | null);
    enabled?: boolean;
    notes?: (string | null);
};

