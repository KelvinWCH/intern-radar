import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import type { DuplicatedJobs, DuplicateReason } from '../models/job.models';
import { PostedDate } from '../posted-date/posted-date';
import { JobsService } from '../jobs.service';
import { apiError } from '../../shared/api-error';

@Component({
  selector: 'app-duplicated-jobs',
  imports: [DatePipe, RouterLink, PostedDate],
  templateUrl: './duplicated-jobs.html',
  styleUrl: './duplicated-jobs.scss',
})
export class DuplicatedJobsPanel {
  readonly duplicates = input<DuplicatedJobs>();
  private readonly service = inject(JobsService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly descriptions = signal(new Map<string, string | null>());
  protected readonly loading = signal(new Set<string>());
  protected readonly errors = signal(new Map<string, string>());

  protected loadDescription(id: string): void {
    if (this.loading().has(id) || this.descriptions().has(id)) {
      return;
    }
    this.loading.update((ids) => new Set([...ids, id]));
    this.errors.update((errors) => {
      const next = new Map(errors);
      next.delete(id);
      return next;
    });
    this.service
      .description(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (description): void => {
          this.descriptions.update((items) => new Map(items).set(id, description));
          this.loading.update((ids) => new Set([...ids].filter((value) => value !== id)));
        },
        error: (error: unknown): void => {
          this.errors.update((items) =>
            new Map(items).set(id, apiError(error, 'Could not load the saved description.')),
          );
          this.loading.update((ids) => new Set([...ids].filter((value) => value !== id)));
        },
      });
  }

  protected reason(reason: DuplicateReason): string {
    switch (reason) {
      case 'identical_extraction_input':
        return 'Identical content and extraction context. The AI result can be reused';
      case 'same_url':
        return 'Same normalized posting URL. Check the descriptions';
      case 'same_employer_id':
        return 'Same employer ID, company and job site. Check this match';
      case 'conflicting_employer_ids':
        return 'Same URL, different employer IDs. These may be different jobs';
    }
  }
}
