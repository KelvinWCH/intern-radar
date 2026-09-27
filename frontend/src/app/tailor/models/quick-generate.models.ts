import type { JobSummary } from '../../jobs/models/job.models';

export type QuickGenerateJob = Pick<JobSummary, 'id' | 'company' | 'title'>;

export type QuickGenerateState =
  | { readonly status: 'idle' }
  | { readonly status: 'starting' }
  | { readonly status: 'running'; readonly documentId: string }
  | { readonly status: 'ready'; readonly documentId: string }
  | {
      readonly status: 'failed';
      readonly documentId: string | null;
      readonly error: string;
    };
