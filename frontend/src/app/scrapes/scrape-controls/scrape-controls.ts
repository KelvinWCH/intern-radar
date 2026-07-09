import { DatePipe, DecimalPipe, DOCUMENT, TitleCasePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ProgressBarModule } from 'primeng/progressbar';
import type { Subscription } from 'rxjs';
import { EMPTY, catchError, exhaustMap, startWith, takeWhile } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { LoadingIndicator } from '../../shared/loading-indicator/loading-indicator';
import { formatTokens } from '../../shared/usage-format';
import { visiblePoll } from '../../shared/visible-poll';
import { scrapeStageLabels } from '../constants/scrape-stage.constants';
import type { ScrapeSource, ScrapeTask } from '../models/scrape.models';
import { duration } from '../models/scrape.models';
import { scrapeTriggerLabel } from '../models/trigger.models';
import { ScrapeStatusStore } from '../scrape-status.store';
import { ScrapesService } from '../scrapes.service';
import { requestId } from '../../shared/request-id';

@Component({
  selector: 'app-scrape-controls',
  imports: [
    FormsModule,
    RouterLink,
    DatePipe,
    DecimalPipe,
    TitleCasePipe,
    ProgressBarModule,
    LoadingIndicator,
  ],
  templateUrl: './scrape-controls.html',
  styleUrl: './scrape-controls.scss',
})
export class ScrapeControls {
  private readonly service = inject(ScrapesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  private poll: Subscription | null = null;
  private activityPoll: Subscription | undefined;
  private sourcesRequest: Subscription | undefined;
  private taskRequest: Subscription | undefined;
  private stepsRequest: Subscription | undefined;
  private requestId: string | null = null;
  protected readonly sources = signal<readonly ScrapeSource[]>([]);
  protected readonly selected = signal<ReadonlySet<string>>(new Set());
  protected readonly allSelected = computed((): boolean => {
    const available = this.sources().filter((source): boolean => source.enabled);
    return (
      available.length > 0 && available.every((source): boolean => this.selected().has(source.id))
    );
  });
  protected readonly group = signal('github');
  protected readonly filter = signal('');
  protected readonly visible = computed((): readonly ScrapeSource[] =>
    this.sources().filter(
      (source): boolean =>
        source.group === this.group() &&
        source.name.toLowerCase().includes(this.filter().toLowerCase()),
    ),
  );
  protected readonly task = inject(ScrapeStatusStore).task;
  protected readonly activity = inject(ScrapeStatusStore).activity;
  protected readonly external = inject(ScrapeStatusStore).external;
  protected readonly activityLoading = inject(ScrapeStatusStore).activityLoading;
  protected readonly activityError = inject(ScrapeStatusStore).activityError;
  private readonly taskLoading = inject(ScrapeStatusStore).taskLoading;
  private readonly taskError = inject(ScrapeStatusStore).taskError;
  protected readonly blocked = computed(
    (): boolean =>
      this.active() ||
      this.activityLoading() ||
      !!this.activityError() ||
      (this.activity()?.busy ?? false),
  );
  protected readonly scrapeTriggerLabel = scrapeTriggerLabel;
  protected readonly scrapeStageLabels = scrapeStageLabels;
  protected readonly active = computed(
    (): boolean => this.task()?.status === 'queued' || this.task()?.status === 'running',
  );
  protected readonly stage = computed((): string => {
    const task = this.task();
    if (!task || task.status === 'queued') {
      return 'Waiting to start';
    }
    if (task.cancel_requested) {
      return 'Stopping…';
    }
    const phase = task.progress.phase;
    return phase === null ? 'Starting next source' : (scrapeStageLabels[phase] ?? phase);
  });
  protected readonly loading = signal(true);
  protected readonly pending = signal(false);
  protected readonly error = signal('');
  protected readonly duration = duration;
  protected readonly formatTokens = formatTokens;
  protected runtime = 30;
  protected calls = 20;
  protected useAi = false;
  protected downloads = 100;
  protected age = 2;
  protected includeOlderPostings = false;
  constructor() {
    inject(ScrapeStatusStore).attachControls(this.destroyRef);
    this.load();
  }
  protected load(): void {
    this.sourcesRequest?.unsubscribe();
    this.taskRequest?.unsubscribe();
    this.stepsRequest?.unsubscribe();
    this.poll?.unsubscribe();
    this.activityPoll?.unsubscribe();
    this.activityLoading.set(true);
    this.activityError.set('');
    this.taskLoading.set(true);
    this.taskError.set('');
    this.activityPoll = visiblePoll(this.document, 5000, 5000)
      .pipe(
        startWith(0),
        exhaustMap(() =>
          this.service.activity().pipe(
            catchError((error: unknown) => {
              this.activityLoading.set(false);
              this.activityError.set(
                apiError(error, 'Could not check running importers. Reconnect to retry.'),
              );
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((activity): void => {
        this.activity.set(activity);
        this.activityLoading.set(false);
        this.activityError.set('');
      });
    this.loading.set(true);
    this.error.set('');
    this.sourcesRequest = this.service
      .sources()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sources): void => {
          this.sources.set(sources);
          this.loading.set(false);
          if (!this.selected().size) {
            this.selected.set(
              new Set(
                sources
                  .filter((source): boolean => source.id === 'github:simplify-summer2027')
                  .map((source): string => source.id),
              ),
            );
          }
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not load scrape sources.'));
        },
      });
    this.taskRequest = this.service
      .tasks()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (tasks): void => {
          this.taskLoading.set(false);
          const task =
            tasks.find((item): boolean => item.status === 'queued' || item.status === 'running') ??
            tasks[0];
          if (task) {
            this.task.set(task);
            this.watch(task);
            if (task.status !== 'queued' && task.status !== 'running') {
              this.loadSteps(task);
            }
          } else {
            this.task.set(null);
          }
        },
        error: (error: unknown): void => {
          this.taskLoading.set(false);
          this.taskError.set(apiError(error, 'Could not read scrape status.'));
          this.error.set(this.taskError());
        },
      });
  }
  protected toggle(id: string): void {
    const selected = new Set(this.selected());
    if (selected.has(id)) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
    this.selected.set(selected);
  }
  protected selectVisible(): void {
    this.selected.set(
      new Set([
        ...this.selected(),
        ...this.visible()
          .filter((source): boolean => source.enabled)
          .map((source): string => source.id),
      ]),
    );
  }
  protected selectAll(): void {
    this.selected.set(
      new Set(
        this.sources()
          .filter((source): boolean => source.enabled)
          .map((source): string => source.id),
      ),
    );
  }
  protected clear(): void {
    this.selected.set(new Set());
  }
  protected start(): void {
    if (this.blocked() || this.pending() || !this.selected().size) {
      return;
    }
    this.taskRequest?.unsubscribe();
    this.stepsRequest?.unsubscribe();
    this.pending.set(true);
    this.error.set('');
    this.requestId ??= requestId();
    this.service
      .start({
        request_id: this.requestId,
        sources: [...this.selected()],
        max_runtime_seconds: this.runtime * 60,
        use_ai: this.useAi,
        max_ai_calls: this.calls,
        max_downloads: this.downloads,
        max_age_days: this.includeOlderPostings ? 2 : this.age,
        include_older_postings: this.includeOlderPostings,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (task): void => {
          this.taskLoading.set(false);
          this.taskError.set('');
          this.task.set(task);
          this.pending.set(false);
          this.requestId = null;
          this.useAi = false;
          this.watch(task);
        },
        error: (error: unknown): void => {
          this.pending.set(false);
          this.taskLoading.set(false);
          if (!(error instanceof HttpErrorResponse) || error.status !== 0) {
            this.requestId = null;
          }
          this.error.set(
            apiError(error, 'Could not start this scrape. Check source selections and limits.'),
          );
        },
      });
  }
  protected cancel(): void {
    const task = this.task();
    if (!task || this.pending()) {
      return;
    }
    this.pending.set(true);
    this.service
      .cancel(task.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated): void => {
          this.task.set(updated);
          this.pending.set(false);
        },
        error: (error: unknown): void => {
          this.pending.set(false);
          this.error.set(apiError(error, 'Could not request cancellation.'));
        },
      });
  }
  private loadSteps(task: ScrapeTask): void {
    this.stepsRequest?.unsubscribe();
    this.stepsRequest = this.service
      .task(task.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (current): void => {
          if (this.task()?.id === current.id) {
            this.task.set(current);
          }
        },
        error: (): void => {
          // the summary is still useful without the step log
        },
      });
  }
  private watch(task: ScrapeTask): void {
    this.poll?.unsubscribe();
    if (task.status !== 'queued' && task.status !== 'running') {
      return;
    }
    this.poll = visiblePoll(this.document, 1000, 2000)
      .pipe(
        exhaustMap(() =>
          this.service.task(task.id).pipe(
            catchError((error: unknown) => {
              this.taskError.set(
                apiError(error, 'Live scrape updates delayed. Retrying automatically.'),
              );
              this.error.set(this.taskError());
              return EMPTY;
            }),
          ),
        ),
        takeWhile(
          (current): boolean => current.status === 'queued' || current.status === 'running',
          true,
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (current): void => {
          if (this.error() === this.taskError()) {
            this.error.set('');
          }
          this.taskError.set('');
          this.task.set(current);
        },
      });
  }
}
