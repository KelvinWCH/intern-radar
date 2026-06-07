import type { ApplicationStatus } from '../../jobs/models/user-data.models';
import { parseStatus } from '../../jobs/models/user-data.models';
import * as validation from '../../shared/api-validation';

export type ActivityKind =
  | 'job_added'
  | 'job_saved'
  | 'application_updated'
  | 'application_marked'
  | 'documents_generated'
  | 'resume_updated';
export interface ActivityDay {
  readonly date: string;
  readonly actions: number;
  readonly applications: number;
  readonly documents: number;
  readonly resume_updates: number;
}
export interface ActivityData {
  readonly job_id: string | null;
  readonly company: string | null;
  readonly title: string | null;
  readonly status: ApplicationStatus | null;
  readonly document_id: string | null;
  readonly profile_revision: number | null;
  readonly backfilled: boolean;
}
export interface ActivityEvent {
  readonly id: string;
  readonly kind: ActivityKind;
  readonly occurred_at: number;
  readonly data: ActivityData;
}
export interface ActivitySummary {
  readonly start_date: string;
  readonly end_date: string;
  readonly generated_at: number;
  readonly total_applications: number;
  readonly active_days: number;
  readonly days: readonly ActivityDay[];
  readonly pipeline: readonly { readonly status: ApplicationStatus; readonly count: number }[];
  readonly recent: readonly ActivityEvent[];
}

function count(value: unknown): number {
  const result = validation.number(value);
  if (!Number.isSafeInteger(result)) {
    throw new Error('Invalid activity count.');
  }
  return result;
}
function day(value: unknown): string {
  const result = validation.text(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result)) {
    throw new Error('Invalid activity date.');
  }
  return result;
}
function kind(value: unknown): ActivityKind {
  if (
    value === 'job_added' ||
    value === 'job_saved' ||
    value === 'application_updated' ||
    value === 'application_marked' ||
    value === 'documents_generated' ||
    value === 'resume_updated'
  ) {
    return value;
  }
  throw new Error('Invalid activity kind.');
}

export function parseActivitySummary(value: unknown): ActivitySummary {
  const row = validation.object(value);
  return {
    start_date: day(row['start_date']),
    end_date: day(row['end_date']),
    generated_at: count(row['generated_at']),
    total_applications: count(row['total_applications']),
    active_days: count(row['active_days']),
    days: validation.list(row['days'], (value): ActivityDay => {
      const entry = validation.object(value);
      return {
        date: day(entry['date']),
        actions: count(entry['actions']),
        applications: count(entry['applications']),
        documents: count(entry['documents']),
        resume_updates: count(entry['resume_updates']),
      };
    }),
    pipeline: validation.list(row['pipeline'], (value) => {
      const entry = validation.object(value);
      return { status: parseStatus(entry['status']), count: count(entry['count']) };
    }),
    recent: validation.list(row['recent'], (value): ActivityEvent => {
      const entry = validation.object(value);
      const data = validation.object(entry['data']);
      return {
        id: validation.text(entry['id']),
        kind: kind(entry['kind']),
        occurred_at: count(entry['occurred_at']),
        data: {
          job_id: data['job_id'] === null ? null : validation.identifier(data['job_id']),
          company: validation.optionalText(data['company']),
          title: validation.optionalText(data['title']),
          status: data['status'] === null ? null : parseStatus(data['status']),
          document_id: validation.optionalText(data['document_id']),
          profile_revision:
            data['profile_revision'] === null ? null : count(data['profile_revision']),
          backfilled: validation.boolean(data['backfilled']),
        },
      };
    }),
  };
}
