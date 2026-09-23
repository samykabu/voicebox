/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PronunciationSubstitution } from './PronunciationSubstitution';
/**
 * What the engine would actually be given, and why it differs.
 */
export type PronunciationPreviewResponse = {
    original: string;
    result: string;
    applied: Array<PronunciationSubstitution>;
};

