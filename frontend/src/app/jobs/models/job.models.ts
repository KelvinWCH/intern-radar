import { identifier, isRecord } from '../../shared/api-validation';
import type { JobDetails } from './job-details.models';
import { parseJobDetails } from './job-details.models';
import type { JobUserData } from './user-data.models';
import { parseUserData } from './user-data.models';

export type SourceType = 'scraped' | 'user_added' | 'user_auto_add';

export type ReviewReason = 'security_challenge' | 'linkedin_blocked' | 'robots_disallowed';

export interface JobInput extends Partial<Omit<JobDetails, 'raw_description'>> {
  readonly company: string;
  readonly title: string;
  readonly raw_description: string;
  readonly application_url: string | null;
}

export type MatchBand = 'strong' | 'good' | 'fair' | 'low';

export interface JobMatch {
  readonly score: number;
  readonly band: MatchBand;
  readonly reasons: readonly string[];
  readonly skills: readonly string[];
  readonly role: string | null;
  readonly components: Readonly<Record<string, number>>;
  readonly scoredAt: number;
}

export interface JobSummary {
  readonly reviewReason?: ReviewReason | null;
  readonly cleanedDescription?: string | null;
  readonly deletedAt?: number | null;
  readonly prestige?: boolean;
  readonly companyTier?: 'tech' | 'known' | null;
  readonly metadata?: JobMetadata;
  readonly match?: JobMatch | null;
  readonly copies?: number;
  readonly details?: JobDetails;
  readonly detailsVersion?: number;
  readonly duplicatedJobs?: DuplicatedJobs;
  readonly user: JobUserData;
  readonly id: string;
  readonly sourceType: SourceType;
  readonly company: string;
  readonly title: string;
  readonly locations: readonly string[];
  readonly terms: readonly string[];
  readonly category: string | null;
  readonly summary: string | null;
  readonly applicationUrl: string | null;
  readonly rawDescription: string | null;
  readonly applyUrl: string | null;
  readonly firstSeenAt: number;
  readonly isTorontoArea?: boolean | null;
}

export type ClosedReason = 'not_listed' | 'upstream_closed' | 'link_check';

export interface LinkCheck {
  readonly checkedAt: number;
  readonly status: 'open' | 'closed' | 'unknown';
  readonly detail: string;
  readonly url: string;
  readonly finalUrl: string | null;
}

export interface JobMetadata {
  readonly source: string | null;
  readonly lastSeenAt: number | null;
  readonly detailsUpdatedAt: number | null;
  readonly closedAt?: number | null;
  readonly closedReason?: ClosedReason | null;
  readonly closedDetail?: string | null;
  readonly linkCheck?: LinkCheck | null;
}

export interface JobPage {
  readonly items: readonly JobSummary[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error('Invalid jobs response.');
  }
  return value;
}

function text(value: unknown): string {
  if (typeof value !== 'string') {
    throw new Error('Expected job text.');
  }
  return value;
}

function nullableText(value: unknown): string | null {
  return value === null ? null : text(value);
}

function integer(value: unknown, minimum = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum) {
    throw new Error('Invalid job number.');
  }
  return value;
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    throw new Error('Invalid job labels.');
  }
  return value.map((item: unknown): string => text(item));
}

function webUrl(value: unknown): string {
  const url = new URL(text(value));
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('Invalid job link.');
  }
  return url.href;
}

function parsePrestige(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new Error('Invalid company priority.');
  }
  return value;
}

function parseCompanyTier(value: unknown): 'tech' | 'known' | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (value === 'tech' || value === 'known') {
    return value;
  }
  throw new Error('Invalid company tier.');
}

function sourceType(value: unknown): SourceType {
  if (value === 'scraped' || value === 'user_added' || value === 'user_auto_add') {
    return value;
  }
  throw new Error('Invalid job source type.');
}

function closedReason(value: unknown): ClosedReason | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (value === 'not_listed' || value === 'upstream_closed' || value === 'link_check') {
    return value;
  }
  throw new Error('Invalid job closure reason.');
}

function linkCheck(value: unknown): LinkCheck | null {
  if (value === null || value === undefined) {
    return null;
  }
  const check = record(value);
  const status = check['status'];
  if (status !== 'open' && status !== 'closed' && status !== 'unknown') {
    throw new Error('Invalid posting check status.');
  }
  return {
    checkedAt: integer(check['checked_at']),
    status,
    detail: text(check['detail']),
    url: webUrl(check['url']),
    finalUrl: check['final_url'] == null ? null : webUrl(check['final_url']),
  };
}

function matchBand(value: unknown): MatchBand {
  if (value === 'strong' || value === 'good' || value === 'fair' || value === 'low') {
    return value;
  }
  throw new Error('Invalid match band.');
}

export function parseMatch(value: unknown): JobMatch | null {
  if (value === null || value === undefined) {
    return null;
  }
  const row = record(value);
  const components = record(row['components']);
  return {
    score: integer(row['score']),
    band: matchBand(row['band']),
    reasons: strings(row['reasons']),
    skills: strings(row['skills']),
    role: row['role'] === null || row['role'] === undefined ? null : text(row['role']),
    components: Object.fromEntries(
      Object.entries(components).map(([key, part]): [string, number] => {
        if (typeof part !== 'number' || part < 0 || part > 1) {
          throw new Error('Invalid match component.');
        }
        return [key, part];
      }),
    ),
    scoredAt: integer(row['scored_at']),
  };
}

function reviewReason(value: unknown): ReviewReason | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (
    value === 'security_challenge' ||
    value === 'linkedin_blocked' ||
    value === 'robots_disallowed'
  ) {
    return value;
  }
  throw new Error('Invalid job review reason.');
}

export function parseJob(value: unknown): JobSummary {
  const job = record(value);
  return {
    reviewReason: reviewReason(job['review_reason']),
    cleanedDescription: nullableText(job['cleaned_description'] ?? null),
    deletedAt: job['deleted_at'] == null ? null : integer(job['deleted_at']),
    companyTier: parseCompanyTier(job['company_tier']),
    metadata: {
      source: nullableText(job['source'] ?? null),
      lastSeenAt: job['last_seen_at'] == null ? null : integer(job['last_seen_at']),
      detailsUpdatedAt:
        job['details_updated_at'] == null ? null : integer(job['details_updated_at']),
      closedAt: job['closed_at'] == null ? null : integer(job['closed_at']),
      closedReason: closedReason(job['closed_reason']),
      closedDetail: nullableText(job['closed_detail'] ?? null),
      linkCheck: linkCheck(job['link_check']),
    },
    match: parseMatch(job['match']),
    copies: job['copies'] === undefined ? 1 : integer(job['copies'], 1),
    details: parseJobDetails(value),
    detailsVersion: integer(job['details_version'] ?? 0),
    duplicatedJobs: parseDuplicatedJobs(job['duplicated_jobs']),
    user: parseUserData(job['user']),
    id: identifier(job['id']),
    sourceType: sourceType(job['source_type']),
    prestige: job['prestige'] === undefined ? false : parsePrestige(job['prestige']),
    company: text(job['company']),
    title: text(job['title']),
    locations: strings(job['locations']),
    terms: strings(job['terms']),
    category: nullableText(job['category']),
    summary: nullableText(job['summary']),
    applicationUrl: job['application_url'] === null ? null : webUrl(job['application_url']),
    rawDescription: nullableText(job['raw_description']),
    applyUrl: job['apply_url'] === null ? null : webUrl(job['apply_url']),
    firstSeenAt: integer(job['first_seen_at']),
    isTorontoArea: typeof job['is_toronto_area'] === 'boolean' ? job['is_toronto_area'] : null,
  };
}

export type DuplicateReason =
  'identical_extraction_input' | 'same_url' | 'same_employer_id' | 'conflicting_employer_ids';

export interface DuplicatedJob {
  readonly id: string;
  readonly source: string;
  readonly externalId: string;
  readonly company: string;
  readonly title: string;
  readonly sourceJobId: string | null;
  readonly applicationUrl: string | null;
  readonly sourceUrl: string | null;
  readonly listingUrl?: string | null;
  readonly rawDescription: string | null;
  readonly firstSeenAt: number;
  readonly matchReason: DuplicateReason;
  readonly datePosted?: number | null;
}

export interface DuplicatedJobs {
  readonly items: readonly DuplicatedJob[];
}

function duplicateReason(value: unknown): DuplicateReason {
  if (
    value === 'identical_extraction_input' ||
    value === 'same_url' ||
    value === 'same_employer_id' ||
    value === 'conflicting_employer_ids'
  ) {
    return value;
  }
  throw new Error('Invalid duplicate match reason.');
}

function parseDuplicatedJobs(value: unknown): DuplicatedJobs {
  if (value === undefined) {
    return { items: [] };
  }
  const items: unknown = record(value)['items'];
  if (!Array.isArray(items)) {
    throw new Error('Invalid duplicated jobs.');
  }
  return {
    items: items.map((value: unknown): DuplicatedJob => {
      const item = record(value);
      return {
        id: identifier(item['id']),
        source: text(item['source']),
        externalId: text(item['external_id']),
        company: text(item['company']),
        title: text(item['title']),
        sourceJobId: nullableText(item['source_job_id']),
        applicationUrl: item['application_url'] === null ? null : webUrl(item['application_url']),
        sourceUrl: item['source_url'] === null ? null : webUrl(item['source_url']),
        listingUrl:
          item['listing_url'] === null || item['listing_url'] === undefined
            ? null
            : webUrl(item['listing_url']),
        rawDescription: nullableText(item['raw_description']),
        firstSeenAt: integer(item['first_seen_at']),
        datePosted: item['date_posted'] == null ? null : integer(item['date_posted']),
        matchReason: duplicateReason(item['match_reason']),
      };
    }),
  };
}

export function parseJobPage(value: unknown): JobPage {
  const page = record(value);
  const items: unknown = page['items'];
  if (!Array.isArray(items)) {
    throw new Error('Invalid jobs page.');
  }
  const result = {
    items: items.map((item: unknown): JobSummary =>
      parseJob({
        ...record(item),
        raw_description: null,
        cleaned_description: null,
        qualifications: null,
      }),
    ),
    total: integer(page['total']),
    limit: integer(page['limit'], 1),
    offset: integer(page['offset']),
  };
  if (
    result.limit > 100 ||
    result.items.length > result.limit ||
    (result.items.length > 0 && result.offset + result.items.length > result.total) ||
    (result.items.length === 0 && result.offset < result.total)
  ) {
    throw new Error('Inconsistent jobs page.');
  }
  return result;
}
