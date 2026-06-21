import {
  defaultReportFilters,
  gtaLocationPatterns,
  reportFiltersStorageKey,
} from '../constants/report-filters.constants';
import { isRecord } from '../../shared/api-validation';
import type { JobSummary } from '../models/job.models';
import type { CompanyGroup, ReportFilters } from '../models/report-filters.models';

export function isGta(job: JobSummary): boolean {
  return (
    job.isTorontoArea === true ||
    job.locations.some((place): boolean =>
      gtaLocationPatterns.some((pattern): boolean => pattern.test(place)),
    )
  );
}

function tierRank(job: JobSummary): number {
  if (job.companyTier === 'tech') {
    return 0;
  }
  if (job.companyTier === 'known' || job.prestige) {
    return 1;
  }
  return 2;
}

function priority(job: JobSummary): number {
  return (isGta(job) ? 0 : 3) + tierRank(job);
}

export function filterJobs(
  jobs: readonly JobSummary[],
  filters: ReportFilters,
): readonly JobSummary[] {
  const search = filters.search.trim().toLowerCase();
  const matching = jobs.filter(
    (job): boolean =>
      (filters.area === 'canada' || isGta(job)) &&
      (filters.source === 'all' ||
        (filters.source === 'scraped'
          ? job.sourceType === 'scraped'
          : job.sourceType !== 'scraped')) &&
      (!filters.hideApplied || job.user.status === 'new' || job.user.status === 'saved') &&
      (!search ||
        `${job.title} ${job.company} ${job.locations.join(' ')}`.toLowerCase().includes(search)),
  );
  return filters.prestigeFirst
    ? matching.sort((a, b): number => priority(a) - priority(b))
    : matching;
}

export function groupByCompany(jobs: readonly JobSummary[]): readonly CompanyGroup[] {
  const groups = new Map<string, JobSummary[]>();
  for (const job of jobs) {
    const company = job.company.trim() || 'Unknown company';
    const members = groups.get(company);
    if (members) {
      members.push(job);
    } else {
      groups.set(company, [job]);
    }
  }
  return Array.from(groups, ([company, members]): CompanyGroup => ({ company, jobs: members }));
}

export function loadFilters(): ReportFilters {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(reportFiltersStorageKey) ?? 'null');
    if (!isRecord(saved)) {
      return defaultReportFilters;
    }
    return {
      area: saved['area'] === 'canada' ? 'canada' : 'gta',
      source: saved['source'] === 'scraped' || saved['source'] === 'mine' ? saved['source'] : 'all',
      search: '',
      hideApplied: saved['hideApplied'] === true,
      prestigeFirst: saved['prestigeFirst'] !== false,
      groupByCompany: saved['groupByCompany'] === true,
    };
  } catch {
    return defaultReportFilters;
  }
}

export function saveFilters(filters: ReportFilters): void {
  try {
    localStorage.setItem(reportFiltersStorageKey, JSON.stringify({ ...filters, search: '' }));
  } catch {
    // storage can be blocked, filters still work for this visit
  }
}
