import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { apiError } from '../../shared/api-error';
import { JobFields } from '../job-fields/job-fields';
import { JobsService } from '../jobs.service';
import { changedDetails, draftDetails, jobDraft } from '../models/job-details.models';
import type { JobSummary } from '../models/job.models';
import { PostedDate } from '../posted-date/posted-date';
import { SourceBadge } from '../source-badge/source-badge';

@Component({
  selector: 'app-add-job',
  imports: [FormsModule, RouterLink, SourceBadge, JobFields, PostedDate],
  templateUrl: './add-job.html',
  styleUrl: './add-job.scss',
})
export class AddJob {
  private readonly service = inject(JobsService);
  private readonly destroyRef = inject(DestroyRef);
  protected draft = jobDraft();
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly saved = signal<JobSummary | null>(null);
  protected canSave(): boolean {
    return this.draft.raw_description.trim().length > 0 && !this.saving();
  }

  protected save(): void {
    if (!this.canSave()) {
      return;
    }
    this.error.set('');
    this.saved.set(null);
    let details;
    try {
      details = draftDetails(this.draft);
    } catch (error: unknown) {
      this.error.set(error instanceof Error ? error.message : 'Check the job details.');
      return;
    }
    this.saving.set(true);
    this.service
      .add({
        ...changedDetails(details, draftDetails(jobDraft())),
        company: details.company,
        title: details.title,
        application_url: details.application_url,
        raw_description: this.draft.raw_description.trim(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job): void => {
          this.saving.set(false);
          this.saved.set(job);
          this.draft = jobDraft();
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(
            apiError(error, 'Could not save this job. Your inputs are still here; try again.'),
          );
        },
      });
  }
}
