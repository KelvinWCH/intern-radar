import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs';
import { list } from '../shared/api-validation';
import { AiDefaults } from '../settings/ai-defaults';
import type {
  ScrapeActivity,
  ScrapeHistoryPage,
  ScrapeRequest,
  ScrapeSource,
  ScrapeTask,
} from './models/scrape.models';
import {
  parseScrapeActivity,
  parseScrapeHistory,
  parseScrapeSource,
  parseScrapeTask,
} from './models/scrape.models';
@Injectable({ providedIn: 'root' })
export class ScrapesService {
  private readonly http = inject(HttpClient);
  private readonly preferences = inject(AiDefaults);
  activity(): Observable<ScrapeActivity> {
    return this.http.get<unknown>('/api/scrapes/activity').pipe(map(parseScrapeActivity));
  }
  sources(): Observable<readonly ScrapeSource[]> {
    return this.http
      .get<unknown>('/api/scrapes/sources')
      .pipe(map((value): ScrapeSource[] => list(value, parseScrapeSource)));
  }
  tasks(): Observable<readonly ScrapeTask[]> {
    return this.http
      .get<unknown>('/api/scrapes')
      .pipe(map((value): ScrapeTask[] => list(value, parseScrapeTask)));
  }
  task(id: string): Observable<ScrapeTask> {
    return this.http
      .get<unknown>(`/api/scrapes/${encodeURIComponent(id)}`)
      .pipe(map(parseScrapeTask));
  }
  start(request: ScrapeRequest): Observable<ScrapeTask> {
    const model = request.ai_model ?? this.preferences.options('scrape').model;
    return this.http
      .post<unknown>('/api/scrapes', {
        ...request,
        ...(request.use_ai && model ? { ai_model: model } : {}),
      })
      .pipe(map(parseScrapeTask));
  }
  cancel(id: string): Observable<ScrapeTask> {
    return this.http
      .post<unknown>(`/api/scrapes/${encodeURIComponent(id)}/cancel`, {})
      .pipe(map(parseScrapeTask));
  }
  cancelScheduled(id: string): Observable<ScrapeActivity> {
    return this.http
      .post<unknown>(`/api/scrapes/scheduled/${encodeURIComponent(id)}/cancel`, {})
      .pipe(map(parseScrapeActivity));
  }
  history(offset = 0, source = '', status = '', cursor = ''): Observable<ScrapeHistoryPage> {
    const params: Record<string, string | number> = { offset, limit: 20, cursor };
    if (source) {
      params['source'] = source;
    }
    if (status) {
      params['status'] = status;
    }
    return this.http.get<unknown>('/api/scrapes/history', { params }).pipe(
      map((value): ScrapeHistoryPage => {
        const page = parseScrapeHistory(value);
        if (page.offset !== offset || page.limit !== 20 || (cursor && page.nextCursor === cursor)) {
          throw new Error('Unexpected scrape history page.');
        }
        return page;
      }),
    );
  }
}
