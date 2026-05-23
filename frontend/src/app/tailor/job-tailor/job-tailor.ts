import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { TextareaModule } from 'primeng/textarea';
import type { Observable } from 'rxjs';
import type { DocumentSummary } from '../../jobs/models/user-data.models';
import { apiError } from '../../shared/api-error';
import { countCharacters } from '../../shared/text-count';
import { TextCount } from '../../shared/text-count/text-count';
import { tailoringDescriptionLimit } from '../../jobs/constants/description.constants';
import type { AiModelOptions } from '../../shared/models/ai.models';
import { validAiOptions } from '../../shared/models/ai.models';
import { StageModels } from '../stage-models/stage-models';
import { DocumentsService } from '../documents.service';
import { pendingTailoringAttempt } from '../pending-attempt';
import type { DocumentDetail, TailoringMode } from '../models/document.models';
import { loadTailoringMode, oneShotDefaults } from '../constants/tailoring-mode.constants';
import { requestId } from '../../shared/request-id';

@Component({
  selector: 'app-job-tailor',
  imports: [
    FormsModule,
    RouterLink,
    StageModels,
    ButtonModule,
    CheckboxModule,
    TextareaModule,
    TextCount,
  ],
  templateUrl: './job-tailor.html',
  styleUrl: './job-tailor.scss',
})
export class JobTailor {
  readonly jobId = input.required<string>();
  readonly hasDescription = input(true);
  readonly cleanedDescription = input<string | null>(null);
  protected readonly descriptionTooLong = computed(
    (): boolean => countCharacters(this.cleanedDescription() ?? '') > tailoringDescriptionLimit,
  );
  readonly documents = input<readonly DocumentSummary[]>([]);
  readonly completed = output<DocumentDetail>();
  readonly attempted = output();
  private readonly service = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  private requestId: string | null = null;
  private watchedId: string | null = null;
  protected readonly progress = signal<DocumentDetail | null>(null);
  private readonly started = signal(false);
  readonly consoleDocument = this.progress.asReadonly();
  readonly consoleVisible = computed((): boolean => this.started() || this.progress() !== null);
  protected resume = true;
  protected letter = true;
  protected instructions = '';
  protected readonly aiOptions = signal<AiModelOptions>({});
  protected readonly researchOptions = signal<AiModelOptions>({});
  protected readonly letterOptions = signal<AiModelOptions>({});
  protected readonly reviewerOptions = signal<AiModelOptions>({});
  protected readonly tailoringMode = signal<TailoringMode>(loadTailoringMode());
  protected readonly oneShotOptions = signal<AiModelOptions>({ ...oneShotDefaults });
  protected readonly researchUrl = signal('');
  protected readonly validOptions = validAiOptions;
  protected readonly working = signal(false);
  readonly consoleWorking = this.working.asReadonly();
  protected readonly controlsDisabled = computed(
    (): boolean => this.working() || this.progress()?.status === 'running',
  );
  protected readonly error = signal('');
  readonly consoleError = this.error.asReadonly();
  protected readonly result = signal<DocumentDetail | null>(null);
  protected readonly hasVersion = computed((): boolean =>
    this.documents().some((document): boolean => document.status === 'completed'),
  );

  constructor() {
    effect((): void => {
      const active = pendingTailoringAttempt(this.documents());
      untracked((): void => {
        if (active && active.id !== this.watchedId && !this.working()) {
          this.started.set(true);
          this.watchedId = active.id;
          this.requestId = active.id;
          this.working.set(true);
          this.follow(this.service.watch(active.id));
        }
      });
    });
  }

  protected generationOptionsChanged(): void {
    this.requestId = null;
  }

  protected tailor(): void {
    const pending = this.progress();
    if (pending?.status === 'running' && !this.working()) {
      this.working.set(true);
      this.error.set('');
      this.follow(this.service.watch(pending.id));
      return;
    }
    if (
      this.working() ||
      (!this.resume && !this.letter) ||
      this.descriptionTooLong() ||
      (this.tailoringMode() === 'one_shot'
        ? !validAiOptions(this.oneShotOptions())
        : !validAiOptions(this.researchOptions()) ||
          !validAiOptions(this.reviewerOptions()) ||
          (this.resume && !validAiOptions(this.aiOptions())) ||
          (this.letter && !validAiOptions(this.letterOptions())))
    ) {
      return;
    }
    if (pending?.status === 'awaiting_review' && pending.review) {
      this.requestId = null;
    }
    this.working.set(true);
    this.started.set(true);
    this.error.set('');
    this.result.set(null);
    this.requestId ??= requestId();
    const instructions = this.instructions.trim();
    this.progress.set(null);
    this.follow(
      this.service.tailor(this.jobId(), {
        request_id: this.requestId,
        include_resume: this.resume,
        include_cover_letter: this.letter,
        ai_options: this.resume ? this.aiOptions() : {},
        research_ai_options: this.researchOptions(),
        reviewer_ai_options: this.reviewerOptions(),
        resume_ai_options: this.resume ? this.aiOptions() : {},
        cover_letter_ai_options: this.letter ? this.letterOptions() : {},
        mode: this.tailoringMode(),
        ...(this.tailoringMode() === 'one_shot'
          ? { one_shot_ai_options: this.oneShotOptions() }
          : {}),
        ...(this.researchUrl().trim() ? { company_research_url: this.researchUrl().trim() } : {}),
        ...(instructions ? { instructions } : {}),
      }),
    );
  }

  researchUpdated(document: DocumentDetail): void {
    this.error.set('');
    this.progress.set(document);
    this.working.set(document.status === 'running');
    this.follow(this.service.watch(document.id, document));
  }

  controlled(document: DocumentDetail): void {
    this.progress.set(document);
    if (document.status === 'cancelled' && !this.working()) {
      this.stopped();
    }
  }

  private stopped(): void {
    this.requestId = null;
    this.attempted.emit();
  }

  private follow(source: Observable<DocumentDetail>): void {
    source.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result): void => {
        this.progress.set(result);
        this.watchedId = result.id;
        if (result.status === 'running') {
          return;
        }
        this.working.set(false);
        if (result.status === 'awaiting_review') {
          this.attempted.emit();
          return;
        }
        if (result.status === 'cancelled') {
          this.stopped();
          return;
        }
        if (result.status === 'failed') {
          this.requestId = null;
          this.error.set(result.error ?? 'Tailoring failed. Your application status is unchanged.');
          this.attempted.emit();
          return;
        }
        this.result.set(result);
        this.requestId = null;
        this.completed.emit(result);
      },
      error: (error: unknown): void => {
        this.working.set(false);
        if (
          this.progress()?.status !== 'running' &&
          (!(error instanceof HttpErrorResponse) || error.status !== 0)
        ) {
          this.requestId = null;
        }
        this.error.set(
          apiError(
            error,
            'Could not confirm tailoring. Your job is saved; check document history before retrying.',
          ),
        );
        this.attempted.emit();
      },
    });
  }
}
