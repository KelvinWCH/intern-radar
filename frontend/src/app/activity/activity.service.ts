import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs';
import type { ActivitySummary } from './models/activity.models';
import { parseActivitySummary } from './models/activity.models';

@Injectable({ providedIn: 'root' })
export class ActivityService {
  private readonly http = inject(HttpClient);

  summary(days: number): Observable<ActivitySummary> {
    return this.http
      .get<unknown>('/api/activity/summary', { params: { days } })
      .pipe(map(parseActivitySummary));
  }
}
