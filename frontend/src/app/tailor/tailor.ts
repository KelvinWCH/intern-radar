import { Location } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { TextareaModule } from 'primeng/textarea';
import type { Observable } from 'rxjs';
import { map, of, switchMap } from 'rxjs';
import { JobsService } from '../jobs/jobs.service';
import { tailoringDescriptionLimit } from '../jobs/constants/description.constants';
import { countCharacters } from '../shared/text-count';
import { TextCount } from '../shared/text-count/text-count';
import { jobDraft } from '../jobs/models/job-details.models';
import { PostedDate } from '../jobs/posted-date/posted-date';
import { AiUsageSummary } from '../shared/ai-usage-summary';
import { apiError } from '../shared/api-error';
import { Skeleton } from '../shared/skeleton/skeleton';
import type { AiModelOptions } from '../shared/models/ai.models';
import { validAiOptions } from '../shared/models/ai.models';
import { StageModels } from './stage-models/stage-models';
import { TailoringReports } from './tailoring-reports/tailoring-reports';
import { CoverLetterPreview } from './cover-letter-preview/cover-letter-preview';
import { DocumentActions } from './document-actions/document-actions';
import { DocumentsService } from './documents.service';
import { PdfPreviewDialog } from './pdf-preview-dialog/pdf-preview-dialog';
import { pendingTailoringAttempt } from './pending-attempt';
import type { DocumentDetail, TailoringMode } from './models/document.models';
import type { ResumeProfile } from './models/resume.models';
import { ResumePreview } from './resume-preview/resume-preview';
import { ResumeService } from './resume.service';
import { SourceResumePreview } from './source-resume-preview/source-resume-preview';
import { TailoringConsole } from './tailoring-console/tailoring-console';
import { UnfittedDraftPanel } from './unfitted-draft/unfitted-draft';
import { loadTailoringMode, oneShotDefaults } from './constants/tailoring-mode.constants';
import { canEditResume } from './resume-draft';
import { requestId } from '../shared/request-id';

@Component({
  selector: 'app-tailor',
  imports: [
    FormsModule,
    RouterLink,
    ResumePreview,
    SourceResumePreview,
    CoverLetterPreview,
    DocumentActions,
    PdfPreviewDialog,
    StageModels,
    TailoringReports,
    AiUsageSummary,
    PostedDate,
    ButtonModule,
    CheckboxModule,
    TextareaModule,
    TailoringConsole,
    Skeleton,
    TextCount,
    UnfittedDraftPanel,
  ],
  templateUrl: './tailor.html',
  styleUrl: './tailor.scss',
})
export class Tailor {
  private readonly service = inject(ResumeService);
  private readonly jobs = inject(JobsService);
  private readonly documents = inject(DocumentsService);
  private requestId: string | null = null;
  protected readonly canEditResume = canEditResume;
  protected readonly progress = signal<DocumentDetail | null>(null);
  protected readonly consoleVisible = signal(false);
  protected readonly linkedJob = signal(false);
  protected readonly savedJobId = signal<string | null>(null);
  protected readonly generated = signal<DocumentDetail | null>(null);
  protected readonly includeResume = signal(true);
  protected readonly aiOptions = signal<AiModelOptions>({});
  protected readonly researchOptions = signal<AiModelOptions>({});
  protected readonly letterOptions = signal<AiModelOptions>({});
  protected readonly reviewerOptions = signal<AiModelOptions>({});
  protected readonly tailoringMode = signal<TailoringMode>(loadTailoringMode());
  protected readonly oneShotOptions = signal<AiModelOptions>({ ...oneShotDefaults });
  protected readonly researchUrl = signal('');
  protected readonly includeLetter = signal(true);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly location = inject(Location);
  private readonly destroyRef = inject(DestroyRef);
  private file: File | null = null;
  protected readonly company = signal('');
  protected readonly title = signal('');
  protected readonly description = signal('');
  protected readonly tailoringDescriptionLimit = tailoringDescriptionLimit;
  protected readonly applicationUrl = signal('');
  protected readonly postedDate = signal('');
  protected readonly savedPostedDate = signal<number | null>(null);
  protected readonly closedNotice = signal('');
  protected readonly jobLoading = signal(false);
  protected readonly jobError = signal('');
  protected readonly profile = signal<ResumeProfile | null>(null);
  protected readonly profileStatus = signal<'loading' | 'ready' | 'missing' | 'error'>('loading');
  protected readonly profileError = signal('');
  protected readonly fileName = signal('');
  protected readonly uploading = signal(false);
  protected readonly generating = signal(false);
  protected readonly generationError = signal('');
  protected readonly resultLabel = signal('');
  protected readonly busy = computed(
    (): boolean =>
      this.uploading() ||
      this.generating() ||
      this.jobLoading() ||
      this.progress()?.status === 'running',
  );
  protected readonly canGenerate = computed(
    (): boolean =>
      this.profileStatus() === 'ready' &&
      (this.description().trim().length > 0 ||
        (!!this.company().trim() && !!this.title().trim())) &&
      countCharacters(this.description()) <= tailoringDescriptionLimit &&
      !this.busy() &&
      (this.tailoringMode() === 'one_shot'
        ? validAiOptions(this.oneShotOptions())
        : (!this.includeResume() || validAiOptions(this.aiOptions())) &&
          validAiOptions(this.researchOptions()) &&
          validAiOptions(this.reviewerOptions()) &&
          (!this.includeLetter() || validAiOptions(this.letterOptions()))),
  );
  protected readonly workflowStep = computed((): 1 | 2 | 3 => {
    const status = this.progress()?.status;
    if (status === 'awaiting_review' || status === 'completed') {
      return 3;
    }
    return this.consoleVisible() || this.progress() ? 2 : 1;
  });

  constructor() {
    this.loadProfile();
    this.loadJob();
  }

  protected loadJob(): void {
    const value = this.route.snapshot.queryParamMap.get('job');
    if (value === null) {
      return;
    }
    const id = value;
    if (!id.trim()) {
      this.jobError.set('This saved job link is invalid. You can paste a job below.');
      return;
    }
    this.jobLoading.set(true);
    this.jobError.set('');
    this.jobs
      .get(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (job): void => {
          this.savedJobId.set(job.id);
          this.linkedJob.set(true);
          this.company.set(job.company === 'Not specified' ? '' : job.company);
          this.title.set(job.title === 'Not specified' ? '' : job.title);
          this.description.set(job.cleanedDescription ?? job.rawDescription ?? '');
          this.applicationUrl.set(job.applicationUrl ?? '');
          this.postedDate.set(jobDraft(job.details).date_posted);
          this.savedPostedDate.set(job.details?.date_posted ?? null);
          this.closedNotice.set(
            job.details?.active === false
              ? (job.metadata?.closedDetail ?? 'Its status is set to closed.')
              : '',
          );
          this.jobLoading.set(false);
          const active = pendingTailoringAttempt(job.user.documents);
          if (active) {
            this.consoleVisible.set(true);
            this.requestId = active.id;
            this.generating.set(true);
            this.follow(this.documents.watch(active.id));
          }
        },
        error: (): void => {
          this.jobLoading.set(false);
          this.jobError.set('Could not load this saved job. Retry or paste its description below.');
        },
      });
  }

  protected loadProfile(): void {
    this.profileStatus.set('loading');
    this.profileError.set('');
    this.service
      .profile()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (profile): void => {
          this.profile.set(profile);
          this.profileStatus.set(profile ? 'ready' : 'missing');
        },
        error: (): void => {
          this.profileStatus.set('error');
          this.profileError.set(
            'Could not load your source resume. Check the backend and try again.',
          );
        },
      });
  }

  protected chooseFile(event: Event): void {
    this.file = null;
    this.fileName.set('');
    this.profileError.set('');
    if (!(event.target instanceof HTMLInputElement)) {
      return;
    }
    const file = event.target.files?.item(0);
    if (!file) {
      return;
    }
    if (
      !/\.(pdf|docx|txt|md|tex)$/i.test(file.name) ||
      file.size === 0 ||
      file.size > 5 * 1024 * 1024
    ) {
      this.profileError.set('Choose a nonempty PDF, DOCX, TXT, MD, or TEX file up to 5 MiB.');
      return;
    }
    this.file = file;
    this.fileName.set(file.name);
  }

  protected upload(): void {
    if (!this.file || this.busy()) {
      return;
    }
    this.uploading.set(true);
    this.profileError.set('');
    this.service
      .upload(this.file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (profile): void => {
          this.profile.set(profile);
          this.profileStatus.set('ready');
          this.uploading.set(false);
          this.file = null;
          this.fileName.set('');
          this.generated.set(null);
          this.generationError.set('');
        },
        error: (error: unknown): void => {
          this.uploading.set(false);
          this.profileError.set(this.errorMessage(error, 'Could not save your source resume.'));
        },
      });
  }

  protected targetChanged(): void {
    if (this.savedJobId()) {
      this.rememberTarget(null);
    }
    this.savedJobId.set(null);
    this.requestId = null;
  }

  protected generationOptionsChanged(): void {
    this.requestId = null;
  }

  protected generate(): void {
    const pending = this.progress();
    if (pending?.status === 'running' && !this.generating()) {
      this.generating.set(true);
      this.generationError.set('');
      this.follow(this.documents.watch(pending.id));
      return;
    }
    if (!this.canGenerate() || (!this.includeResume() && !this.includeLetter())) {
      return;
    }
    if (pending?.status === 'awaiting_review' && pending.review) {
      this.requestId = null;
    }
    this.generating.set(true);
    this.consoleVisible.set(true);
    this.generationError.set('');
    this.generated.set(null);
    this.requestId ??= requestId();
    const request = {
      request_id: this.requestId,
      include_resume: this.includeResume(),
      include_cover_letter: this.includeLetter(),
      ai_options: this.includeResume() ? this.aiOptions() : {},
      research_ai_options: this.researchOptions(),
      reviewer_ai_options: this.reviewerOptions(),
      resume_ai_options: this.includeResume() ? this.aiOptions() : {},
      cover_letter_ai_options: this.includeLetter() ? this.letterOptions() : {},
      mode: this.tailoringMode(),
      ...(this.tailoringMode() === 'one_shot'
        ? { one_shot_ai_options: this.oneShotOptions() }
        : {}),
      ...(this.researchUrl().trim() ? { company_research_url: this.researchUrl().trim() } : {}),
    };
    const existing = this.savedJobId();
    const target =
      existing === null
        ? this.jobs
            .forTailoring({
              company: this.company().trim() || 'Not specified',
              title: this.title().trim() || 'Not specified',
              raw_description: this.description().trim(),
              application_url: this.applicationUrl().trim() || null,
              date_posted: this.postedDate()
                ? Math.floor(new Date(`${this.postedDate()}T00:00:00Z`).getTime() / 1000)
                : null,
            })
            .pipe(map((job): string => job.id))
        : of(existing);
    this.progress.set(null);
    this.follow(
      target.pipe(
        switchMap((id) => {
          this.savedJobId.set(id);
          this.rememberTarget(id);
          return this.documents.tailor(id, request);
        }),
      ),
    );
  }

  private rememberTarget(id: string | null): void {
    const url = this.router.createUrlTree(['/tailor'], {
      queryParams: { ...this.route.snapshot.queryParams, job: id },
    });
    this.location.replaceState(this.router.serializeUrl(url));
  }

  protected researchUpdated(document: DocumentDetail): void {
    this.generationError.set('');
    this.progress.set(document);
    this.generating.set(document.status === 'running');
    this.follow(this.documents.watch(document.id, document));
  }

  protected controlled(document: DocumentDetail): void {
    this.progress.set(document);
    if (document.status === 'cancelled' && !this.generating()) {
      this.requestId = null;
    }
  }

  private follow(source: Observable<DocumentDetail>): void {
    source.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (document): void => {
        this.progress.set(document);
        if (document.status === 'running') {
          return;
        }
        this.generating.set(false);
        if (document.status === 'awaiting_review') {
          return;
        }
        if (document.status === 'cancelled') {
          this.requestId = null;
          return;
        }
        if (document.status === 'failed') {
          this.requestId = null;
          this.generationError.set(
            document.error ?? 'Tailoring failed. Your application status is unchanged.',
          );
          return;
        }
        this.generated.set(document);
        this.requestId = null;
        this.resultLabel.set(`${document.title} at ${document.company}`);
      },
      error: (error: unknown): void => {
        this.generating.set(false);
        if (
          this.progress()?.status !== 'running' &&
          (!(error instanceof HttpErrorResponse) || error.status !== 0)
        ) {
          this.requestId = null;
        }
        this.generationError.set(
          apiError(
            error,
            'Could not complete tailoring. Your inputs and saved job are preserved; try again.',
          ),
        );
      },
    });
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (!(error instanceof HttpErrorResponse)) {
      return fallback;
    }
    switch (error.status) {
      case 0:
        return 'Could not reach the backend. Check that it is running, then try again.';
      case 409:
        return 'Upload a source resume before generating a tailored resume.';
      case 413:
        return 'The resume file is too large. Choose a file up to 5 MiB.';
      case 422:
        return 'The document or job details could not be processed. Check the content and configured input limit, then try again.';
      case 502:
        return 'The AI service could not complete this request. Your inputs are preserved; try again.';
      case 503:
        return 'A backend service is not configured. Check the AI connection and document compiler, then try again.';
      default:
        return fallback;
    }
  }
}
