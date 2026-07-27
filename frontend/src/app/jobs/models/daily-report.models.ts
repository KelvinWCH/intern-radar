import type { JobPage, JobSummary } from './job.models';

export interface DailyReportState {
  readonly status: 'loading' | 'ready' | 'error';
  readonly jobs: readonly JobSummary[];
  readonly page?: JobPage;
  readonly error?: string;
}
