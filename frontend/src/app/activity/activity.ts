import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import type { Subscription } from 'rxjs';
import { apiError } from '../shared/api-error';
import { LoadingIndicator } from '../shared/loading-indicator/loading-indicator';
import { Skeleton } from '../shared/skeleton/skeleton';
import { ActivityService } from './activity.service';
import { activityKindLabels, activityRangeDays } from './constants/activity.constants';
import type { ActivityDay, ActivityEvent, ActivitySummary } from './models/activity.models';

@Component({
  selector: 'app-activity',
  imports: [DatePipe, TitleCasePipe, RouterLink, ButtonModule, LoadingIndicator, Skeleton],
  templateUrl: './activity.html',
  styleUrl: './activity.scss',
})
export class Activity {
  private readonly service = inject(ActivityService);
  private readonly destroyRef = inject(DestroyRef);
  private request: Subscription | null = null;
  protected readonly summary = signal<ActivitySummary | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly range = signal(30);
  protected readonly ranges = activityRangeDays;
  protected readonly selectedDay = signal<ActivityDay | null>(null);
  protected readonly maxActions = computed((): number =>
    Math.max(1, ...(this.summary()?.days.map((day) => day.actions) ?? [])),
  );
  protected readonly pipelineTotal = computed(
    (): number => this.summary()?.pipeline.reduce((total, stage) => total + stage.count, 0) ?? 0,
  );
  protected readonly applications = computed(
    (): number => this.summary()?.days.reduce((total, day) => total + day.applications, 0) ?? 0,
  );
  protected readonly documents = computed(
    (): number => this.summary()?.days.reduce((total, day) => total + day.documents, 0) ?? 0,
  );

  constructor() {
    this.load();
  }

  protected load(days = this.range()): void {
    this.request?.unsubscribe();
    this.range.set(days);
    this.loading.set(true);
    this.error.set('');
    this.request = this.service
      .summary(days)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (summary): void => {
          this.summary.set(summary);
          this.selectedDay.set(summary.days.at(-1) ?? null);
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not load activity. Please try again.'));
        },
      });
  }

  protected describeDay(day: ActivityDay): string {
    return `${day.date}: ${String(day.actions)} actions, ${String(day.applications)} applications, ${String(day.documents)} document sets`;
  }

  protected eventLabel(event: ActivityEvent): string {
    return activityKindLabels[event.kind];
  }

  protected eventTime(timestamp: number): string {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(timestamp * 1000);
  }
}
