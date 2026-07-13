import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { relativeTime } from '../../shared/relative-time';
import type { JobDateStatistic } from '../models/job-date.models';
import type { JobSummary } from '../models/job.models';

@Component({
  selector: 'app-job-stats',
  imports: [DatePipe],
  templateUrl: './job-stats.html',
  styleUrl: './job-stats.scss',
})
export class JobStats {
  readonly job = input.required<JobSummary>();
  private readonly now = signal(Date.now() / 1000);
  protected readonly timezone = Intl.DateTimeFormat()
    .resolvedOptions()
    .timeZone.replaceAll('_', ' ');
  protected readonly dates = computed((): readonly JobDateStatistic[] => {
    const job = this.job();
    const employer = (value: number | null | undefined): boolean =>
      value !== null && value !== undefined && value % 86_400 === 0;
    return [
      {
        label: 'Date posted',
        help: 'When the employer or job board says the posting went live',
        value: job.details?.date_posted,
        dateOnly: employer(job.details?.date_posted),
      },
      {
        label: 'Date scraped',
        help: 'When a scrape first found this posting',
        value: job.sourceType === 'scraped' ? job.firstSeenAt : null,
        dateOnly: false,
      },
      {
        label: 'Last scraped',
        help: 'The most recent scrape that still saw this posting in its source',
        value: job.sourceType === 'scraped' ? job.metadata?.lastSeenAt : null,
        dateOnly: false,
      },
      {
        label: 'Date saved',
        help: 'When this job was first stored in your workspace',
        value: job.firstSeenAt,
        dateOnly: false,
      },
      {
        label: 'Employer updated',
        help: 'When the employer or job board last changed the posting, if it says',
        value: job.details?.date_updated,
        dateOnly: employer(job.details?.date_updated),
      },
      {
        label: 'Last edited',
        help: "When you last edited this job's details or description",
        value: job.metadata?.detailsUpdatedAt,
        dateOnly: false,
      },
    ];
  });

  constructor() {
    const timer = setInterval((): void => {
      this.now.set(Date.now() / 1000);
    }, 15_000);
    inject(DestroyRef).onDestroy((): void => {
      clearInterval(timer);
    });
  }

  protected tooltip(date: JobDateStatistic): string {
    if (date.value === null || date.value === undefined) {
      return 'Not recorded';
    }
    const ago = relativeTime(date.value, this.now());
    return date.dateOnly ? `${ago} (the source only gives a date)` : ago;
  }
}
