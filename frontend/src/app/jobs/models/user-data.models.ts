import * as validation from '../../shared/api-validation';
import type { AiUsage } from '../../shared/models/ai.models';
import { parseAiUsage } from '../../shared/models/ai.models';
import { applicationStatuses } from '../constants/application-status.constants';
export type ApplicationStatus = (typeof applicationStatuses)[number];
export interface DocumentSummary {
  readonly ai_usage?: AiUsage | null;
  readonly id: string;
  readonly job_id: string;
  readonly company: string;
  readonly title: string;
  readonly status: 'running' | 'awaiting_review' | 'completed' | 'failed' | 'cancelled';
  readonly created_at: number;
  readonly date_posted?: number | null;
  readonly finished_at: number | null;
  readonly has_resume: boolean;
  readonly has_cover_letter: boolean;
  readonly error: string | null;
}
export interface JobUserData {
  readonly status: ApplicationStatus;
  readonly notes: string;
  readonly applied_at: number | null;
  readonly follow_up_at: number | null;
  readonly updated_at: number | null;
  readonly version: number;
  readonly documents: readonly DocumentSummary[];
}
export interface JobUserEdit {
  readonly status: ApplicationStatus;
  readonly notes: string;
  readonly applied_at: number | null;
  readonly follow_up_at: number | null;
  readonly version: number;
}
export function parseStatus(value: unknown): ApplicationStatus {
  for (const status of applicationStatuses) {
    if (value === status) {
      return status;
    }
  }
  throw new Error('Invalid application status.');
}
export function parseDocumentSummary(value: unknown): DocumentSummary {
  const row = validation.object(value);
  const status = row['status'];
  if (
    status !== 'running' &&
    status !== 'awaiting_review' &&
    status !== 'completed' &&
    status !== 'failed' &&
    status !== 'cancelled'
  ) {
    throw new Error('Invalid document status.');
  }
  const id = validation.text(row['id']);
  if (!/^[a-f0-9-]{36}$/.test(id)) {
    throw new Error('Invalid document ID.');
  }
  return {
    id,
    ai_usage: parseAiUsage(row['ai_usage']),
    job_id: validation.identifier(row['job_id']),
    company: validation.text(row['company']),
    title: validation.text(row['title']),
    status,
    created_at: validation.number(row['created_at']),
    date_posted: validation.timestamp(row['date_posted'] ?? null),
    finished_at: validation.timestamp(row['finished_at']),
    has_resume: validation.boolean(row['has_resume']),
    has_cover_letter: validation.boolean(row['has_cover_letter']),
    error: validation.optionalText(row['error']),
  };
}
export function parseUserData(value: unknown): JobUserData {
  if (value === undefined) {
    return {
      status: 'new',
      notes: '',
      applied_at: null,
      follow_up_at: null,
      updated_at: null,
      version: 0,
      documents: [],
    };
  }
  const row = validation.object(value);
  return {
    status: parseStatus(row['status']),
    notes: validation.text(row['notes']),
    applied_at: validation.timestamp(row['applied_at']),
    follow_up_at: validation.timestamp(row['follow_up_at']),
    updated_at: validation.timestamp(row['updated_at']),
    version: validation.number(row['version']),
    documents: validation.list(row['documents'], parseDocumentSummary),
  };
}
