import type { JobSummary } from './job.models';

export type ReportArea = 'gta' | 'canada';

export type ReportSource = 'all' | 'scraped' | 'mine';

export interface ReportFilters {
  readonly area: ReportArea;
  readonly source: ReportSource;
  readonly search: string;
  readonly hideApplied: boolean;
  readonly prestigeFirst: boolean;
  readonly groupByCompany: boolean;
}

export interface CompanyGroup {
  readonly company: string;
  readonly jobs: readonly JobSummary[];
}
