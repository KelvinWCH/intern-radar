import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs';
import { object, optionalText } from '../shared/api-validation';
import type { ScrapeSummary } from '../scrapes/models/scrape-summary.models';
import { parseScrapeSummary } from '../scrapes/models/scrape-summary.models';
import { localDate, moveDay, startOfDay } from './job-day';
import type { CalendarDateBasis, CalendarDayCount } from './models/job-calendar.models';
import type { JobEdit } from './models/job-details.models';
import type { JobOverview, JobQuery } from './models/job-query.models';
import { parseOverview } from './models/job-query.models';
import type { JobInput, JobPage, JobSummary } from './models/job.models';
import { parseJob, parseJobPage } from './models/job.models';
import type { JobUserData, JobUserEdit } from './models/user-data.models';
import { parseUserData } from './models/user-data.models';

@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly http = inject(HttpClient);

  description(id: string): Observable<string | null> {
    return this.http
      .get<unknown>(`/api/jobs/${encodeURIComponent(id)}/description`)
      .pipe(map((value): string | null => optionalText(object(value)['raw_description'])));
  }

  markReviewed(job: JobSummary): Observable<JobSummary> {
    return this.http
      .post<unknown>(`/api/jobs/${encodeURIComponent(job.id)}/review`, {
        version: job.detailsVersion ?? 0,
      })
      .pipe(map(parseJob));
  }

  retryScrape(job: JobSummary): Observable<JobSummary> {
    return this.http
      .post<unknown>(`/api/jobs/${encodeURIComponent(job.id)}/retry-scrape`, {
        version: job.detailsVersion ?? 0,
      })
      .pipe(map(parseJob));
  }

  checkLink(job: JobSummary): Observable<JobSummary> {
    return this.http
      .post<unknown>(`/api/jobs/${encodeURIComponent(job.id)}/check-link`, {})
      .pipe(map(parseJob));
  }

  updateDetails(id: string, edit: JobEdit): Observable<JobSummary> {
    return this.http
      .patch<unknown>(`/api/jobs/${encodeURIComponent(id)}`, edit)
      .pipe(map(parseJob));
  }

  browse(
    query: JobQuery,
    offset = 0,
    limit = 30,
    dateBasis: CalendarDateBasis = 'scraped',
  ): Observable<JobPage> {
    const params: Record<string, string | number | boolean> = {
      scope: query.scope ?? 'all',
      limit,
      offset,
      activity: query.activity,
      tracked: query.tracked,
      sort: query.sort,
      deleted: query.deleted ?? false,
    };
    if (query.flagged !== undefined) {
      params['flagged'] = query.flagged;
    }
    if (query.match) {
      params['min_match'] = Number(query.match);
    }
    if (query.toronto) {
      params['toronto_area'] = true;
    }
    for (const key of ['q', 'company', 'location', 'source', 'application_status'] as const) {
      if (query[key]) {
        params[key] = query[key];
      }
    }
    if (dateBasis === 'posted') {
      if (query.from) {
        params['posted_from'] = query.from;
      }
      if (query.before) {
        params['posted_before'] = localDate(moveDay(new Date(`${query.before}T00:00:00`), 1));
      }
      params['posted_timezone'] = Intl.DateTimeFormat().resolvedOptions().timeZone;
    } else {
      if (query.from) {
        params['first_seen_from'] = Math.floor(new Date(`${query.from}T00:00:00`).getTime() / 1000);
      }
      if (query.before) {
        const after = new Date(`${query.before}T00:00:00`);
        after.setDate(after.getDate() + 1);
        params['first_seen_before'] = Math.floor(after.getTime() / 1000);
      }
    }
    return this.http.get<unknown>('/api/jobs', { params }).pipe(
      map((response): JobPage => {
        const page = parseJobPage(response);
        if (page.offset !== offset || page.limit !== limit) {
          throw new Error('Unexpected jobs page offset.');
        }
        return page;
      }),
    );
  }

  forCalendar(
    query: JobQuery,
    start: Date,
    days: CalendarDayCount = 7,
    offset = 0,
    dateBasis: CalendarDateBasis = 'scraped',
  ): Observable<JobPage> {
    const bounded = {
      ...query,
      from: localDate(start),
      before: localDate(moveDay(start, days - 1)),
    };
    return this.browse(bounded, offset, 100, dateBasis);
  }

  delete(id: string): Observable<JobSummary> {
    return this.http.delete<unknown>(`/api/jobs/${encodeURIComponent(id)}`).pipe(map(parseJob));
  }

  restore(id: string): Observable<JobSummary> {
    return this.http
      .post<unknown>(`/api/jobs/${encodeURIComponent(id)}/restore`, {})
      .pipe(map(parseJob));
  }

  overview(deleted = false, scope: JobQuery['scope'] = 'all'): Observable<JobOverview> {
    return this.http
      .get<unknown>('/api/jobs/overview', {
        params: { ...(deleted ? { deleted: true } : {}), scope },
      })
      .pipe(map(parseOverview));
  }

  forTailoring(job: JobInput): Observable<JobSummary> {
    return this.http.post<unknown>('/api/jobs/for-tailoring', job).pipe(map(parseJob));
  }

  updateUser(id: string, edit: JobUserEdit): Observable<JobUserData> {
    return this.http
      .put<unknown>(`/api/jobs/${encodeURIComponent(id)}/user`, edit)
      .pipe(map(parseUserData));
  }

  add(job: JobInput): Observable<JobSummary> {
    return this.http.post<unknown>('/api/jobs', job).pipe(map(parseJob));
  }

  get(id: string): Observable<JobSummary> {
    return this.http.get<unknown>(`/api/jobs/${encodeURIComponent(id)}`).pipe(map(parseJob));
  }

  scrapeSummaryForDay(day: Date): Observable<ScrapeSummary> {
    return this.http
      .get<unknown>('/api/import-runs/summary', {
        params: {
          from_timestamp: Math.floor(startOfDay(day).getTime() / 1000),
          before_timestamp: Math.floor(moveDay(day, 1).getTime() / 1000),
        },
      })
      .pipe(map(parseScrapeSummary));
  }

  forDay(day: Date, offset = 0): Observable<JobPage> {
    const from = Math.floor(startOfDay(day).getTime() / 1000);
    const before = Math.floor(moveDay(day, 1).getTime() / 1000);
    return this.http
      .get<unknown>('/api/jobs', {
        params: { first_seen_from: from, first_seen_before: before, limit: 100, offset },
      })
      .pipe(
        map((response): JobPage => {
          const page = parseJobPage(response);
          if (page.offset !== offset || page.limit !== 100) {
            throw new Error('Unexpected jobs page offset.');
          }
          return page;
        }),
      );
  }
}
