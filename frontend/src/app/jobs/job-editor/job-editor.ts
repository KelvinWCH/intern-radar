import { NgTemplateOutlet } from '@angular/common';
import {
  afterNextRender,
  Component,
  DestroyRef,
  computed,
  ElementRef,
  inject,
  Injector,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../shared/api-error';
import { countCharacters } from '../../shared/text-count';
import { TextCount } from '../../shared/text-count/text-count';
import {
  storedDescriptionLimit,
  tailoringDescriptionLimit,
} from '../constants/description.constants';
import type { DescriptionBlock } from '../description-blocks';
import { descriptionBlocks } from '../description-blocks';
import { JobFields } from '../job-fields/job-fields';
import { JobsService } from '../jobs.service';
import type { JobDetails } from '../models/job-details.models';
import { changedDetails, draftDetails, jobDraft } from '../models/job-details.models';
import type { JobSummary } from '../models/job.models';

@Component({
  selector: 'app-job-editor',
  imports: [FormsModule, JobFields, NgTemplateOutlet, TextCount],
  templateUrl: './job-editor.html',
  styleUrl: './job-editor.scss',
})
export class JobEditor {
  readonly job = input.required<JobSummary>();
  readonly saved = output<JobSummary>();
  private readonly service = inject(JobsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private original: JobDetails = draftDetails(jobDraft());
  private version = 0;
  private jobId = '';
  protected draft = jobDraft();
  protected readonly storedDescriptionLimit = storedDescriptionLimit;
  protected readonly tailoringDescriptionLimit = tailoringDescriptionLimit;
  protected readonly editing = signal<'details' | 'description' | null>(null);
  protected readonly blocks = computed((): DescriptionBlock[] =>
    descriptionBlocks(this.job().cleanedDescription ?? this.job().rawDescription ?? ''),
  );
  protected readonly descriptionTooLong = computed(
    (): boolean =>
      countCharacters(this.job().cleanedDescription ?? this.job().rawDescription ?? '') >
      tailoringDescriptionLimit,
  );
  protected readonly showRawSource = computed((): boolean => {
    const { cleanedDescription, rawDescription } = this.job();
    return (
      !!rawDescription?.trim() && !!cleanedDescription && cleanedDescription !== rawDescription
    );
  });
  protected readonly descriptionOpen = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly message = signal('');

  protected begin(section: 'details' | 'description' = 'details'): void {
    const job = this.job();
    if (!job.details) {
      return;
    }
    this.draft = jobDraft(job.details);
    this.original = draftDetails(this.draft);
    this.version = job.detailsVersion ?? 0;
    this.jobId = job.id;
    this.editing.set(section);
    this.error.set('');
    this.message.set('');
    afterNextRender(
      (): void => {
        this.element.nativeElement
          .querySelector<HTMLElement>(
            section === 'description' ? '#edit-description' : '#new-title',
          )
          ?.focus();
      },
      { injector: this.injector },
    );
  }
  protected save(): void {
    if (this.saving()) {
      return;
    }
    this.error.set('');
    let changes;
    try {
      changes = changedDetails(draftDetails(this.draft), this.original);
    } catch (error: unknown) {
      this.error.set(error instanceof Error ? error.message : 'Check the job details.');
      return;
    }
    if (!Object.keys(changes).length) {
      this.editing.set(null);
      return;
    }
    this.saving.set(true);
    this.service
      .updateDetails(this.jobId, { ...changes, version: this.version })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job): void => {
          this.saving.set(false);
          this.editing.set(null);
          this.message.set('Job details saved. Future scrapes will keep your corrections.');
          this.saved.emit(job);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(apiError(error, 'Could not save job details. Your draft is preserved.'));
        },
      });
  }
  protected reload(): void {
    this.saving.set(true);
    this.service
      .get(this.jobId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job): void => {
          this.saving.set(false);
          if (!job.details) {
            return;
          }
          this.draft = jobDraft(job.details);
          this.original = draftDetails(this.draft);
          this.version = job.detailsVersion ?? 0;
          this.error.set('');
          this.saved.emit(job);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(
            apiError(error, 'Could not reload the saved details. Your draft is preserved.'),
          );
        },
      });
  }
}
