import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import type { Subscription } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { LoadingIndicator } from '../../shared/loading-indicator/loading-indicator';
import { Skeleton } from '../../shared/skeleton/skeleton';
import { applicationStatuses } from '../constants/application-status.constants';
import type { ApplicationStatus } from '../models/user-data.models';
import { calendarDateModes, calendarDayCounts } from '../constants/calendar.constants';
import { groupPostings } from '../job-calendar';
import { moveDay, startOfDay, startOfWeek } from '../job-day';
import { JobWeek } from '../job-week/job-week';
import { MatchBadge } from '../match-badge/match-badge';
import { JobsService } from '../jobs.service';
import type {
  CalendarDateBasis,
  CalendarDayCount,
  JobPostingGroup,
} from '../models/job-calendar.models';
import type { JobOverview, JobQuery } from '../models/job-query.models';
import type { JobPage, JobSummary } from '../models/job.models';
import { PostedDate } from '../posted-date/posted-date';
import { QuickGenerate } from '../../tailor/quick-generate/quick-generate';
import { RelatedPostings } from '../related-postings/related-postings';

function statusChangeMessage(
  company: string,
  previous: ApplicationStatus,
  next: ApplicationStatus,
): string {
  if (next === 'new') {
    return `${company}: untracked. The job is still in Jobs.`;
  }
  if (previous === 'applied' && next === 'saved') {
    return `${company}: application undone. Kept in Saved.`;
  }
  return `${company}: status updated.`;
}

@Component({
  selector: 'app-job-library',
  imports: [
    FormsModule,
    RouterLink,
    DatePipe,
    TitleCasePipe,
    PostedDate,
    RelatedPostings,
    QuickGenerate,
    JobWeek,
    MatchBadge,
    LoadingIndicator,
    Skeleton,
  ],
  templateUrl: './job-library.html',
  styleUrls: [
    './job-library.scss',
    './job-library-controls.scss',
    './job-library-loading.scss',
    './job-library-status.scss',
    './job-library-calendar.scss',
  ],
})
export class JobLibrary {
  private readonly service = inject(JobsService);
  private readonly destroyRef = inject(DestroyRef);
  private request: Subscription | null = null;
  private typing: ReturnType<typeof setTimeout> | null = null;
  private loadVersion = 0;
  private overviewRequest: Subscription | undefined;
  protected readonly tracker = inject(ActivatedRoute).snapshot.data['tracker'] === true;
  protected readonly view = signal<'week' | 'list'>(this.tracker ? 'list' : 'week');
  protected readonly calendarDayCounts = calendarDayCounts;
  protected readonly calendarDateModes = calendarDateModes;
  protected readonly dateBasis = signal<CalendarDateBasis>('scraped');
  protected readonly calendarDescription = computed(
    (): string =>
      this.calendarDateModes.find((mode): boolean => mode.value === this.dateBasis())
        ?.description ?? '',
  );
  protected readonly dayCount = signal<CalendarDayCount>(3);
  protected readonly rangeStart = signal(moveDay(new Date(), -2));
  protected readonly rangeEnd = computed((): Date =>
    moveDay(this.rangeStart(), this.dayCount() - 1),
  );
  protected readonly currentRange = computed(
    (): boolean => this.rangeStart().getTime() >= this.latestRangeStart().getTime(),
  );
  protected readonly pendingIds = signal<readonly string[]>([]);
  protected readonly deletedJob = signal<JobSummary | null>(null);
  protected readonly actionError = signal('');
  protected readonly statusMessage = signal('');
  protected readonly statuses = applicationStatuses;
  protected filters: JobQuery = {
    scope: this.tracker ? 'all' : 'eligible',
    q: '',
    company: '',
    location: '',
    source: '',
    application_status: '',
    activity: 'all',
    tracked: this.tracker,
    sort: 'match',
    match: '',
    toronto: false,
    from: '',
    before: '',
  };
  protected readonly advanced = signal(false);
  protected readonly page = signal<JobPage | null>(null);
  protected readonly displayPage = computed(
    (): JobPage =>
      this.page() ?? {
        items: [],
        total: 0,
        limit: this.view() === 'week' ? 100 : 30,
        offset: 0,
      },
  );
  protected readonly listGroups = computed((): readonly JobPostingGroup[] =>
    groupPostings(this.displayPage().items),
  );
  protected readonly overview = signal<JobOverview | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  constructor() {
    this.load();
    this.loadOverview();
    this.destroyRef.onDestroy((): void => {
      if (this.typing !== null) {
        clearTimeout(this.typing);
      }
    });
  }

  private loadOverview(): void {
    this.overviewRequest?.unsubscribe();
    this.overview.set(null);
    this.overviewRequest = this.service
      .overview(this.filters.deleted ?? false, this.filters.scope)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (overview): void => {
          this.overview.set(overview);
        },
        error: (): void => {
          this.overview.set(null);
        },
      });
  }
  protected load(offset = 0): void {
    if (this.typing !== null) {
      clearTimeout(this.typing);
      this.typing = null;
    }
    this.loadVersion++;
    this.actionError.set('');
    this.request?.unsubscribe();
    this.loading.set(true);
    this.page.set(null);
    this.error.set('');
    this.request = (
      this.view() === 'week'
        ? this.service.forCalendar(
            this.filters,
            this.rangeStart(),
            this.dayCount(),
            offset,
            this.dateBasis(),
          )
        : this.service.browse(this.filters, offset)
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page): void => {
          this.page.set(page);
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not load jobs. Try again.'));
        },
      });
  }

  protected typed(): void {
    if (this.typing !== null) {
      clearTimeout(this.typing);
    }
    this.typing = setTimeout((): void => {
      this.typing = null;
      this.load();
    }, 350);
  }

  protected setView(view: 'week' | 'list'): void {
    if (this.view() === view) {
      return;
    }
    this.view.set(view);
    this.load();
  }

  protected setDateBasis(basis: CalendarDateBasis): void {
    if (basis === this.dateBasis()) {
      return;
    }
    this.dateBasis.set(basis);
    this.load();
  }

  protected changeRange(direction: -1 | 0 | 1): void {
    if (this.loading() || (direction >= 0 && this.currentRange())) {
      return;
    }
    const latest = this.latestRangeStart();
    const next = direction ? moveDay(this.rangeStart(), direction * this.dayCount()) : latest;
    this.rangeStart.set(next > latest ? latest : next);
    this.load();
  }

  protected setDayCount(days: CalendarDayCount): void {
    if (this.loading() || days === this.dayCount()) {
      return;
    }
    const today = startOfDay(new Date());
    const anchor = this.rangeEnd() > today ? today : this.rangeEnd();
    this.dayCount.set(days);
    this.rangeStart.set(days === 7 ? startOfWeek(anchor) : moveDay(anchor, 1 - days));
    this.load();
  }

  private latestRangeStart(): Date {
    const today = startOfDay(new Date());
    return this.dayCount() === 7 ? startOfWeek(today) : moveDay(today, 1 - this.dayCount());
  }

  protected toggleDeleted(): void {
    this.filters.deleted = !this.filters.deleted;
    this.view.set(
      this.filters.deleted || this.tracker || this.filters.scope === 'all' ? 'list' : 'week',
    );
    this.loadOverview();
    this.load();
  }

  protected toggleAllScraped(): void {
    const scope = this.filters.scope === 'all' ? 'eligible' : 'all';
    this.filters.scope = scope;
    delete this.filters.flagged;
    this.filters.deleted = false;
    this.view.set(scope === 'all' ? 'list' : 'week');
    this.loadOverview();
    this.load();
  }

  protected toggleFlagged(): void {
    const flagged = !this.filters.flagged;
    if (flagged) {
      this.filters.flagged = true;
      this.filters.scope = 'all';
    } else {
      delete this.filters.flagged;
      this.filters.scope = this.tracker ? 'all' : 'eligible';
    }
    this.filters.deleted = false;
    this.filters.tracked = flagged ? false : this.tracker;
    this.view.set('list');
    this.loadOverview();
    this.load();
  }

  protected deleteJob(job: JobSummary): void {
    this.changeDeletion(job, true);
  }

  protected restoreJob(job: JobSummary): void {
    this.changeDeletion(job, false);
  }

  protected selectJobStatus(job: JobSummary, control: HTMLSelectElement): void {
    const status = this.statuses.find((candidate): boolean => candidate === control.value);
    control.value = job.user.status;
    if (status) {
      this.changeStatus(job, status);
    }
  }

  protected changeStatus(job: JobSummary, status: ApplicationStatus): void {
    if (status === job.user.status || this.pendingIds().includes(job.id) || this.loading()) {
      return;
    }
    const loadVersion = this.loadVersion;
    this.pendingIds.update((ids): readonly string[] => [...ids, job.id]);
    this.actionError.set('');
    this.statusMessage.set('');
    this.service
      .updateUser(job.id, {
        status,
        notes: job.user.notes,
        applied_at: status === 'new' || status === 'saved' ? null : job.user.applied_at,
        follow_up_at: job.user.follow_up_at,
        version: job.user.version,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (user): void => {
          this.pendingIds.update((ids): readonly string[] =>
            ids.filter((id): boolean => id !== job.id),
          );
          this.statusMessage.set(statusChangeMessage(job.company, job.user.status, status));
          if (loadVersion !== this.loadVersion) {
            this.load(this.page()?.offset ?? 0);
          } else {
            this.page.update((page): JobPage | null => {
              if (!page) {
                return page;
              }
              const keep =
                (!this.filters.tracked || user.status !== 'new') &&
                (!this.filters.application_status ||
                  this.filters.application_status === user.status);
              return {
                ...page,
                total: keep ? page.total : Math.max(0, page.total - 1),
                items: page.items.flatMap((item): JobSummary[] => {
                  if (item.id !== job.id) {
                    return [item];
                  }
                  return keep ? [{ ...item, user }] : [];
                }),
              };
            });
            const page = this.page();
            if (page?.items.length === 0 && page.total > 0) {
              this.load(Math.max(0, page.offset - page.limit));
            }
          }
          this.loadOverview();
        },
        error: (error: unknown): void => {
          this.pendingIds.update((ids): readonly string[] =>
            ids.filter((id): boolean => id !== job.id),
          );
          this.actionError.set(
            apiError(error, 'Could not update status. Your saved status is unchanged.'),
          );
        },
      });
  }

  private changeDeletion(job: JobSummary, deleted: boolean): void {
    if (this.pendingIds().includes(job.id)) {
      return;
    }
    this.pendingIds.update((ids): readonly string[] => [...ids, job.id]);
    this.actionError.set('');
    this.statusMessage.set('');
    (deleted ? this.service.delete(job.id) : this.service.restore(job.id))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated): void => {
          this.pendingIds.update((ids): readonly string[] =>
            ids.filter((id): boolean => id !== job.id),
          );
          this.deletedJob.set(deleted ? updated : null);
          const previous = this.page();
          const offset = previous?.offset ?? 0;
          this.load(previous?.items.length === 1 ? Math.max(0, offset - previous.limit) : offset);
          this.loadOverview();
        },
        error: (error: unknown): void => {
          this.pendingIds.update((ids): readonly string[] =>
            ids.filter((id): boolean => id !== job.id),
          );
          this.actionError.set(
            apiError(
              error,
              deleted ? 'Could not delete job. Try again.' : 'Could not restore job. Try again.',
            ),
          );
        },
      });
  }
  protected resetFilters(): void {
    this.filters = {
      ...this.filters,
      q: '',
      company: '',
      location: '',
      source: '',
      application_status: '',
      activity: 'all',
      match: '',
      toronto: false,
      from: '',
      before: '',
    };
    delete this.filters.flagged;
    this.filters.tracked = this.tracker;
    this.load();
  }
  protected totalCount(): number {
    const counts = this.overview();
    return counts ? counts.total - (this.tracker ? (counts.statuses['new'] ?? 0) : 0) : 0;
  }
  protected initials(company: string): string {
    return company
      .split(/\s+/)
      .slice(0, 2)
      .map((part): string => part.charAt(0))
      .join('')
      .toUpperCase();
  }
  protected companyColor(company: string): number {
    let hash = 0;
    for (const char of company.toLowerCase()) {
      hash += char.charCodeAt(0);
    }
    return hash % 5;
  }
  protected selectStatus(status: string): void {
    this.filters.application_status = this.filters.application_status === status ? '' : status;
    this.load();
  }
}
