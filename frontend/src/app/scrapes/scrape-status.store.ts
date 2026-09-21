import type { DestroyRef } from '@angular/core';
import { Injectable, computed, signal } from '@angular/core';
import { BehaviorSubject, distinctUntilChanged, map } from 'rxjs';
import type { ScrapeActivity, ScrapeTask } from './models/scrape.models';

@Injectable({ providedIn: 'root' })
export class ScrapeStatusStore {
  private readonly mountedControls = new BehaviorSubject(0);
  readonly task = signal<ScrapeTask | null>(null);
  readonly activity = signal<ScrapeActivity | null>(null);
  readonly activityLoading = signal(true);
  readonly activityError = signal('');
  readonly taskLoading = signal(true);
  readonly taskError = signal('');
  readonly external = computed((): boolean => {
    const activity = this.activity();
    if (!activity?.busy) {
      return false;
    }
    return (
      !!activity.scheduled ||
      activity.runs.some((run): boolean => run.trigger === 'cron' || run.trigger === 'cli') ||
      (this.task()?.status !== 'queued' && this.task()?.status !== 'running')
    );
  });
  readonly controlled = this.mountedControls.pipe(
    map((count): boolean => count > 0),
    distinctUntilChanged(),
  );

  attachControls(destroyRef: DestroyRef): void {
    this.mountedControls.next(this.mountedControls.value + 1);
    destroyRef.onDestroy((): void => {
      this.mountedControls.next(this.mountedControls.value - 1);
    });
  }
}
