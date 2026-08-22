import { parseJob } from './job.models';

const job = {
  id: 'job-1',
  source: 'greenhouse-example',
  source_type: 'scraped',
  details_version: 2,
  company: 'Example',
  title: 'Software Intern',
  application_url: 'https://example.com/jobs/1',
  apply_url: null,
  source_job_id: null,
  raw_description: null,
  locations: ['Toronto'],
  terms: [],
  category: null,
  summary: null,
  active: false,
  date_posted: null,
  date_updated: null,
  first_seen_at: 1_790_000_000,
  last_seen_at: 1_790_000_000,
  details_updated_at: null,
  user: {
    status: 'new',
    notes: '',
    applied_at: null,
    follow_up_at: null,
    updated_at: null,
    version: 0,
    documents: [],
  },
};

describe('parseJob closure details', (): void => {
  it('reads closure details', (): void => {
    const parsed = parseJob({
      ...job,
      closed_at: 1_790_086_400,
      closed_reason: 'not_listed',
      closed_detail: "No longer listed on the employer's job board.",
      link_check: {
        checked_at: 1_790_090_000,
        status: 'unknown',
        detail: 'The site answered HTTP 429; try again later.',
        url: 'https://example.com/jobs/1',
        final_url: 'https://example.com/jobs/1?ref=x',
      },
    });
    expect(parsed.metadata?.closedReason).toBe('not_listed');
    expect(parsed.metadata?.closedAt).toBe(1_790_086_400);
    expect(parsed.metadata?.closedDetail).toBe("No longer listed on the employer's job board.");
    expect(parsed.metadata?.linkCheck).toEqual({
      checkedAt: 1_790_090_000,
      status: 'unknown',
      detail: 'The site answered HTTP 429; try again later.',
      url: 'https://example.com/jobs/1',
      finalUrl: 'https://example.com/jobs/1?ref=x',
    });
  });
});

describe('parseJob match scores', (): void => {
  it('rejects bad match data', (): void => {
    const match = {
      score: 50,
      band: 'fair',
      reasons: [],
      skills: [],
      role: null,
      components: {},
      scored_at: 1,
    };
    expect((): unknown => parseJob({ ...job, match: { ...match, band: 'great' } })).toThrow();
    expect((): unknown =>
      parseJob({ ...job, match: { ...match, components: { role: 1.5 } } }),
    ).toThrow();
  });
});
