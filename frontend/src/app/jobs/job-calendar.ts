import { localDate } from './job-day';
import type { CalendarDateBasis, JobPostingGroup } from './models/job-calendar.models';
import type { JobSummary } from './models/job.models';

function postedDateKey(job: JobSummary): string | null {
  const timestamp = job.details?.date_posted;
  if (timestamp === undefined || timestamp === null) {
    return null;
  }
  const posted = new Date(timestamp * 1000);
  return timestamp % 86_400 === 0 ? posted.toISOString().slice(0, 10) : localDate(posted);
}

export function calendarDateKey(job: JobSummary, basis: CalendarDateBasis): string {
  return (
    (basis === 'posted' ? postedDateKey(job) : null) ?? localDate(new Date(job.firstSeenAt * 1000))
  );
}

function normalized(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase();
}

function postingKeys(job: JobSummary): string[] {
  return [
    `job:${job.id}`,
    ...(job.duplicatedJobs?.items ?? [])
      .filter((related): boolean => related.matchReason !== 'conflicting_employer_ids')
      .map((related): string => `job:${related.id}`),
    [
      'posting',
      normalized(job.company),
      postedDateKey(job) ?? 'unknown',
      normalized(job.title),
      job.locations.map(normalized).sort().join('|'),
    ].join('\n'),
  ];
}

export function groupPostings(jobs: readonly JobSummary[]): JobPostingGroup[] {
  const groups: { lead: JobSummary; keys: Set<string>; members: Set<JobSummary> }[] = [];
  for (const job of jobs) {
    const keys = postingKeys(job);
    const [target, ...merged] = groups.filter((group): boolean =>
      keys.some((key): boolean => group.keys.has(key)),
    );
    if (!target) {
      groups.push({ lead: job, keys: new Set(keys), members: new Set([job]) });
      continue;
    }
    for (const group of merged) {
      for (const key of group.keys) {
        target.keys.add(key);
      }
      for (const member of group.members) {
        target.members.add(member);
      }
      groups.splice(groups.indexOf(group), 1);
    }
    for (const key of keys) {
      target.keys.add(key);
    }
    target.members.add(job);
  }
  return groups.map(({ lead, members }): JobPostingGroup => {
    const postings = jobs.filter((job): boolean => members.has(job));
    return { job: postings.find((job): boolean => job.user.status !== 'new') ?? lead, postings };
  });
}
