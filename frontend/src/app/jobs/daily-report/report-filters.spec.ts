import { defaultReportFilters } from '../constants/report-filters.constants';
import type { JobSummary } from '../models/job.models';
import { filterJobs, isGta } from './report-filters';

function job(
  id: string,
  locations: readonly string[],
  extra: Partial<JobSummary> = {},
): JobSummary {
  return {
    id,
    locations,
    company: `Company ${id}`,
    title: 'Software Intern',
    sourceType: 'scraped',
    terms: [],
    category: null,
    summary: null,
    applicationUrl: null,
    rawDescription: null,
    applyUrl: null,
    firstSeenAt: 0,
    user: {
      status: 'new',
      notes: '',
      applied_at: null,
      follow_up_at: null,
      updated_at: null,
      version: 0,
      documents: [],
    },
    ...extra,
  };
}

describe('daily report filters', (): void => {
  afterEach((): void => {
    localStorage.clear();
  });

  it('matches gta cities', (): void => {
    for (const place of ['Toronto, ON', 'North York, Ontario', 'Markham, ON', 'Mississauga']) {
      expect(isGta(job('1', [place]))).toBe(true);
    }
    expect(isGta(job('1', ['Aurora, ON']))).toBe(true);
    for (const place of ['New York, NY', 'Aurora, IL', 'Vancouver, BC', 'Remote in Canada']) {
      expect(isGta(job('1', [place]))).toBe(false);
    }
    expect(isGta(job('1', ['Remote in Canada'], { isTorontoArea: true }))).toBe(true);
  });

  it('combines filters', (): void => {
    const jobs = [
      job('1', ['Toronto, ON']),
      job('2', ['Ottawa, ON']),
      job('3', ['Markham, ON'], { sourceType: 'user_added', title: 'Data Intern' }),
      job('4', ['Vaughan, ON'], {
        user: { ...job('0', []).user, status: 'applied' },
      }),
    ];
    expect(filterJobs(jobs, defaultReportFilters).map((item) => item.id)).toEqual(['1', '3', '4']);
    expect(filterJobs(jobs, { ...defaultReportFilters, area: 'canada' })).toHaveLength(4);
    expect(
      filterJobs(jobs, { ...defaultReportFilters, source: 'mine' }).map((item) => item.id),
    ).toEqual(['3']);
    expect(
      filterJobs(jobs, { ...defaultReportFilters, hideApplied: true }).map((item) => item.id),
    ).toEqual(['1', '3']);
    expect(
      filterJobs(jobs, { ...defaultReportFilters, search: 'data' }).map((item) => item.id),
    ).toEqual(['3']);
  });
});
