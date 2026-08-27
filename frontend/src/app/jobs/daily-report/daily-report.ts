import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { catchError, map, of, startWith, switchMap } from 'rxjs';
import type { ScrapeSummaryState } from '../../scrapes/models/scrape-summary.models';
import { apiError } from '../../shared/api-error';
import { loadingDailyReportState } from '../constants/daily-report.constants';
import { defaultReportFilters } from '../constants/report-filters.constants';
import { DailyStatistics } from '../daily-statistics/daily-statistics';
import { JobCard } from '../job-card/job-card';
import { localDate, moveDay, startOfDay } from '../job-day';
import { JobsService } from '../jobs.service';
import type { DailyReportState } from '../models/daily-report.models';
import type { JobSummary } from '../models/job.models';
import type { CompanyGroup, ReportFilters } from '../models/report-filters.models';
import { filterJobs, groupByCompany, isGta, loadFilters, saveFilters } from './report-filters';

@Component({
  selector: 'app-daily-report',
  imports: [DatePipe, FormsModule, DailyStatistics, RouterLink, JobCard],
  templateUrl: './daily-report.html',
  styleUrl: './daily-report.scss',
})
export class DailyReport {
  private readonly jobsService = inject(JobsService);
  private readonly request = signal({ day: startOfDay(new Date()), revision: 0 });
  private readonly offset = signal(0);
  private readonly pageRequest = computed(() => ({ ...this.request(), offset: this.offset() }));
  protected readonly selectedDay = computed((): Date => this.request().day);
  protected readonly selectedDate = computed((): string => localDate(this.selectedDay()));
  protected readonly latestDate = localDate(new Date());
  protected readonly isToday = computed(
    (): boolean => this.selectedDay().getTime() === startOfDay(new Date()).getTime(),
  );
  protected readonly timezone = Intl.DateTimeFormat()
    .resolvedOptions()
    .timeZone.replaceAll('_', ' ');
  protected readonly state = toSignal(
    toObservable(this.pageRequest).pipe(
      switchMap(({ day, offset }) =>
        this.jobsService.forDay(day, offset).pipe(
          map((page): DailyReportState => ({ status: 'ready', jobs: page.items, page })),
          startWith(loadingDailyReportState),
          catchError((error: unknown) =>
            of<DailyReportState>({
              status: 'error',
              jobs: [],
              error: apiError(error, 'Check that the backend is running, then try again.'),
            }),
          ),
        ),
      ),
    ),
    { initialValue: loadingDailyReportState },
  );
  protected readonly filters = signal<ReportFilters>(loadFilters());
  protected readonly visibleJobs = computed((): readonly JobSummary[] =>
    filterJobs(this.state().jobs, this.filters()),
  );
  protected readonly companyGroups = computed((): readonly CompanyGroup[] =>
    groupByCompany(this.visibleJobs()),
  );
  protected readonly gtaCount = computed((): number => this.state().jobs.filter(isGta).length);
  protected readonly filtered = computed(
    (): boolean => this.visibleJobs().length !== this.state().jobs.length,
  );
  protected readonly hasFilters = computed((): boolean => {
    const filters = this.filters();
    return (
      filters.area !== 'canada' ||
      filters.source !== 'all' ||
      filters.search.trim().length > 0 ||
      filters.hideApplied
    );
  });
  protected readonly statistics = toSignal(
    toObservable(this.request).pipe(
      switchMap(({ day }) =>
        this.jobsService.scrapeSummaryForDay(day).pipe(
          map((summary): ScrapeSummaryState => ({ status: 'ready', summary })),
          startWith<ScrapeSummaryState>({ status: 'loading', summary: null }),
          catchError(() => of<ScrapeSummaryState>({ status: 'error', summary: null })),
        ),
      ),
    ),
    { initialValue: { status: 'loading', summary: null } satisfies ScrapeSummaryState },
  );

  constructor() {
    effect((): void => {
      saveFilters(this.filters());
    });
  }

  protected setFilter(change: Partial<ReportFilters>): void {
    this.filters.update((current): ReportFilters => ({ ...current, ...change }));
  }

  protected clearFilters(): void {
    this.filters.set({ ...defaultReportFilters, area: 'canada' });
  }

  protected selectDay(value: string): void {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return;
    }
    const day = new Date(`${value}T00:00:00`);
    if (
      !Number.isFinite(day.getTime()) ||
      localDate(day) !== value ||
      day > startOfDay(new Date()) ||
      day.getTime() === this.selectedDay().getTime()
    ) {
      return;
    }
    this.offset.set(0);
    this.request.set({ day, revision: 0 });
  }

  protected changeDay(amount: number): void {
    const day = moveDay(this.selectedDay(), amount);
    if (day <= startOfDay(new Date())) {
      this.offset.set(0);
      this.request.set({ day, revision: 0 });
    }
  }

  protected goToToday(): void {
    this.offset.set(0);
    this.request.update(({ revision }) => ({
      day: startOfDay(new Date()),
      revision: revision + 1,
    }));
  }

  protected refresh(): void {
    this.offset.set(0);
    this.request.update(({ day, revision }) => ({ day, revision: revision + 1 }));
  }

  protected changePage(direction: number): void {
    const page = this.state().page;
    if (!page || this.state().status !== 'ready') {
      return;
    }
    const next = page.offset + direction * page.limit;
    if (next >= 0 && next < page.total) {
      this.offset.set(next);
    }
  }
}
