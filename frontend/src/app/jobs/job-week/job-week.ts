import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, computed, effect, input, output, viewChild } from '@angular/core';
import type { ElementRef } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Skeleton } from '../../shared/skeleton/skeleton';
import { localDate, moveDay } from '../job-day';
import { calendarDateKey, groupPostings } from '../job-calendar';
import type {
  CalendarDateBasis,
  CalendarDayCount,
  JobCalendarDay,
} from '../models/job-calendar.models';
import type { JobSummary } from '../models/job.models';
import { PostedDate } from '../posted-date/posted-date';
import { RelatedPostings } from '../related-postings/related-postings';
import { MatchBadge } from '../match-badge/match-badge';
import { QuickGenerate } from '../../tailor/quick-generate/quick-generate';

@Component({
  selector: 'app-job-week',
  imports: [
    DatePipe,
    TitleCasePipe,
    RouterLink,
    Skeleton,
    PostedDate,
    RelatedPostings,
    MatchBadge,
    QuickGenerate,
  ],
  templateUrl: './job-week.html',
  styleUrls: ['./job-week.scss', './job-week-motion.scss'],
  host: { '[style.--calendar-days]': 'dayCount()', '[class.single-day]': 'dayCount() === 1' },
})
export class JobWeek {
  private readonly viewport = viewChild<ElementRef<HTMLDivElement>>('calendarViewport');
  readonly start = input.required<Date>();
  readonly dayCount = input<CalendarDayCount>(7);
  readonly dateBasis = input<CalendarDateBasis>('scraped');
  readonly jobs = input.required<readonly JobSummary[]>();
  readonly total = input(0);
  readonly loading = input(false);
  readonly unavailable = input(false);
  readonly pendingIds = input<readonly string[]>([]);
  readonly deleteJob = output<JobSummary>();
  protected readonly partial = computed((): boolean => this.total() > this.jobs().length);
  protected readonly days = computed((): readonly JobCalendarDay[] => {
    const today = localDate(new Date());
    return Array.from({ length: this.dayCount() }, (_, index): JobCalendarDay => {
      const date = moveDay(this.start(), index);
      const key = localDate(date);
      return {
        date,
        key,
        today: key === today,
        groups: groupPostings(
          this.jobs().filter((job): boolean => calendarDateKey(job, this.dateBasis()) === key),
        ),
      };
    });
  });

  constructor() {
    effect((): void => {
      this.start();
      this.dayCount();
      this.dateBasis();
      this.loading();
      const viewport = this.viewport()?.nativeElement;
      if (!viewport) {
        return;
      }
      viewport.scrollTop = 0;
      viewport.scrollLeft = 0;
    });
  }
}
