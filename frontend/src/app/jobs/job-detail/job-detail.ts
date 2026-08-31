import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { map, type Subscription } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { Skeleton } from '../../shared/skeleton/skeleton';
import { ApplicationQuestion } from '../../tailor/application-question/application-question';
import { JobDocuments } from '../../tailor/job-documents/job-documents';
import { JobTailor } from '../../tailor/job-tailor/job-tailor';
import { applicationStatuses } from '../constants/application-status.constants';
import { DuplicatedJobsPanel } from '../duplicated-jobs/duplicated-jobs';
import { JobEditor } from '../job-editor/job-editor';
import { JobStats } from '../job-stats/job-stats';
import { MatchBadge } from '../match-badge/match-badge';
import { MatchPanel } from '../match-panel/match-panel';
import { JobsService } from '../jobs.service';
import type { JobSummary } from '../models/job.models';
import type { ApplicationStatus } from '../models/user-data.models';
import { PostedDate } from '../posted-date/posted-date';

function localDate(value: number | null): string {
  if (value === null) {
    return '';
  }
  const date = new Date(value * 1000);
  return `${String(date.getFullYear())}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function dateTimestamp(value: string, previous: number | null): number | null {
  if (value === localDate(previous)) {
    return previous;
  }
  return value ? Math.floor(new Date(`${value}T12:00:00`).getTime() / 1000) : null;
}

@Component({
  selector: 'app-job-detail',
  imports: [
    FormsModule,
    RouterLink,
    DatePipe,
    TitleCasePipe,
    Skeleton,
    JobDocuments,
    JobTailor,
    DuplicatedJobsPanel,
    JobEditor,
    JobStats,
    MatchBadge,
    MatchPanel,
    PostedDate,
    ApplicationQuestion,
  ],
  templateUrl: './job-detail.html',
  styleUrl: './job-detail.scss',
})
export class JobDetail {
  private readonly jobs = inject(JobsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private id = '';
  private editVersion = 0;
  private draftVersion = 0;
  private routeVersion = 0;
  private pendingSave = false;
  private request: Subscription | undefined;
  private reviewAction: Subscription | undefined;
  protected dirty = false;
  protected readonly job = signal<JobSummary | null>(null);
  protected readonly tailorPanel = viewChild(JobTailor);
  protected readonly requestedVersion = toSignal(
    this.route.queryParamMap.pipe(map((params): string | null => params.get('version'))),
    { initialValue: null },
  );
  protected readonly error = signal('');
  protected readonly saveError = signal('');
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly reviewing = signal(false);
  protected readonly retrying = signal(false);
  protected readonly retryMessage = signal('');
  protected readonly checkingLink = signal(false);
  protected readonly linkMessage = signal('');
  protected readonly linkError = signal('');
  private linkAction: Subscription | undefined;
  protected readonly reviewError = signal('');
  protected readonly statuses = applicationStatuses;
  protected status: ApplicationStatus = 'new';
  protected notes = '';
  protected appliedDate = '';
  protected followUp = '';
  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params): void => {
      this.routeVersion++;
      this.pendingSave = false;
      this.saving.set(false);
      this.reviewAction?.unsubscribe();
      this.reviewing.set(false);
      this.retrying.set(false);
      this.retryMessage.set('');
      this.linkAction?.unsubscribe();
      this.checkingLink.set(false);
      this.linkMessage.set('');
      this.linkError.set('');
      this.id = params.get('id') ?? '';
      this.job.set(null);
      this.dirty = false;
      this.saved.set(false);
      this.saveError.set('');
      this.reviewError.set('');
      this.load();
    });
  }
  protected markReviewed(): void {
    const job = this.job();
    if (!job || this.reviewing() || this.retrying()) {
      return;
    }
    this.reviewing.set(true);
    this.reviewError.set('');
    this.retryMessage.set('');
    this.reviewAction = this.jobs
      .markReviewed(job)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated): void => {
          this.reviewing.set(false);
          if (this.id === job.id) {
            this.job.set(updated);
          }
        },
        error: (error: unknown): void => {
          this.reviewing.set(false);
          if (this.id === job.id) {
            this.reviewError.set(
              apiError(error, 'Could not mark this job reviewed. Reload and try again.'),
            );
          }
        },
      });
  }
  protected retryScrape(): void {
    const job = this.job();
    if (!job || this.retrying() || this.reviewing()) {
      return;
    }
    this.retrying.set(true);
    this.reviewError.set('');
    this.retryMessage.set('');
    this.reviewAction = this.jobs
      .retryScrape(job)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated): void => {
          this.retrying.set(false);
          if (this.id !== job.id) {
            return;
          }
          this.job.set(updated);
          this.retryMessage.set(
            updated.reviewReason
              ? 'Still blocked. The saved link and details are preserved.'
              : 'Posting refreshed.',
          );
        },
        error: (error: unknown): void => {
          this.retrying.set(false);
          if (this.id !== job.id) {
            return;
          }
          this.reviewError.set(
            apiError(
              error,
              'Could not retry this posting. The saved link and details are preserved.',
            ),
          );
        },
      });
  }
  protected checkLink(): void {
    const job = this.job();
    if (!job || this.checkingLink()) {
      return;
    }
    this.checkingLink.set(true);
    this.linkMessage.set('');
    this.linkError.set('');
    this.linkAction = this.jobs
      .checkLink(job)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated): void => {
          this.checkingLink.set(false);
          if (this.id !== job.id) {
            return;
          }
          this.job.set(updated);
          const check = updated.metadata?.linkCheck;
          if (!check) {
            return;
          }
          const outcome = {
            open: 'Still open.',
            closed: 'Closed.',
            unknown: 'Could not confirm.',
          }[check.status];
          this.linkMessage.set(`${outcome} ${check.detail}`);
        },
        error: (error: unknown): void => {
          this.checkingLink.set(false);
          if (this.id === job.id) {
            this.linkError.set(apiError(error, 'Could not check this posting. Try again later.'));
          }
        },
      });
  }
  protected load(discardDraft = false): void {
    this.request?.unsubscribe();
    if (discardDraft) {
      this.dirty = false;
    }
    this.error.set('');
    if (!this.id.trim()) {
      this.error.set('Invalid job link.');
      return;
    }
    this.request = this.jobs
      .get(this.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job): void => {
          this.job.set(job);
          if (this.dirty) {
            this.saveError.set(
              'Saved data has refreshed. Your unsaved draft is preserved; reload saved details to discard it.',
            );
            return;
          }
          this.editVersion = job.user.version;
          this.status = job.user.status;
          this.notes = job.user.notes;
          this.appliedDate = localDate(job.user.applied_at);
          this.followUp = localDate(job.user.follow_up_at);
          this.saved.set(false);
          this.saveError.set('');
        },
        error: (error: unknown): void => {
          this.error.set(apiError(error, 'Could not load this job.'));
        },
      });
  }
  protected applicationChanged(): void {
    this.dirty = true;
    this.draftVersion++;
    this.saved.set(false);
  }
  protected changeStatus(status: ApplicationStatus): void {
    this.status = status;
    if (status === 'new' || status === 'saved') {
      this.appliedDate = '';
    }
    if (status === 'applied' && !this.appliedDate) {
      this.appliedDate = localDate(this.job()?.user.applied_at ?? Date.now() / 1000);
    }
    this.applicationChanged();
    this.save();
  }
  protected save(): void {
    const job = this.job();
    if (!job || !this.dirty) {
      return;
    }
    if (this.saving()) {
      this.pendingSave = true;
      return;
    }
    const draftVersion = this.draftVersion;
    const routeVersion = this.routeVersion;
    const appliedDate = this.appliedDate;
    this.pendingSave = false;
    this.saving.set(true);
    this.saved.set(false);
    this.saveError.set('');
    this.jobs
      .updateUser(job.id, {
        status: this.status,
        notes: this.notes,
        applied_at: dateTimestamp(this.appliedDate, job.user.applied_at),
        follow_up_at: dateTimestamp(this.followUp, job.user.follow_up_at),
        version: this.editVersion,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (user): void => {
          if (this.routeVersion !== routeVersion) {
            return;
          }
          this.job.update((current): JobSummary | null =>
            current?.id === job.id ? { ...current, user } : current,
          );
          this.saving.set(false);
          this.editVersion = user.version;
          if (this.appliedDate === appliedDate) {
            this.appliedDate = localDate(user.applied_at);
          }
          this.dirty = this.draftVersion !== draftVersion;
          this.saved.set(!this.dirty);
          if (this.pendingSave) {
            this.save();
          }
        },
        error: (error: unknown): void => {
          if (this.routeVersion !== routeVersion) {
            return;
          }
          this.saving.set(false);
          this.pendingSave = false;
          this.saveError.set(
            apiError(error, 'Could not save application details. Your edits are preserved.'),
          );
        },
      });
  }
}
