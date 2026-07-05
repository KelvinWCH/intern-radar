import type { JobSummary } from './job.models';

export type CalendarDateBasis = 'scraped' | 'posted';

export interface CalendarDateMode {
  readonly value: CalendarDateBasis;
  readonly label: string;
  readonly icon: string;
  readonly description: string;
}

export type CalendarDayCount = 1 | 3 | 5 | 7;

export interface JobPostingGroup {
  readonly job: JobSummary;
  readonly postings: readonly JobSummary[];
}

export interface JobCalendarDay {
  readonly date: Date;
  readonly key: string;
  readonly today: boolean;
  readonly groups: readonly JobPostingGroup[];
}
