import { JsonPipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AiUsageSummary } from '../../shared/ai-usage-summary';
import { apiError } from '../../shared/api-error';
import type { DocumentDetail, DocumentTechnicalDetails } from '../models/document.models';
import type { ReviewDecision } from '../models/application-review.models';
import { DocumentsService } from '../documents.service';
import { ResearchReview } from '../research-review/research-review';
import { ApplicationReviewPanel } from '../application-review/application-review';
import { PdfDiagnosticsPanel } from '../pdf-diagnostics/pdf-diagnostics';
import { JobFit } from '../job-fit/job-fit';

@Component({
  selector: 'app-tailoring-reports',
  imports: [
    JsonPipe,
    AiUsageSummary,
    ResearchReview,
    ApplicationReviewPanel,
    PdfDiagnosticsPanel,
    JobFit,
  ],
  templateUrl: './tailoring-reports.html',
  styleUrl: './tailoring-reports.scss',
})
export class TailoringReports {
  readonly document = input.required<DocumentDetail>();
  readonly expanded = input(true);
  readonly updated = output<DocumentDetail>();
  private readonly service = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly section = signal('review');
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly technical = signal<DocumentTechnicalDetails | null>(null);
  protected readonly technicalLoading = signal(false);
  protected readonly technicalError = signal('');
  protected readonly technicalDocument = computed(() => ({
    ...this.document(),
    ...this.technical(),
  }));
  protected readonly resumeChecks = computed(
    () => this.document().pdf_diagnostics?.find((report) => report.document === 'resume') ?? null,
  );
  private technicalId = '';
  private technicalRequest?: Subscription;

  constructor() {
    effect(() => {
      const id = this.document().id;
      if (id === this.technicalId) {
        return;
      }
      this.technicalId = id;
      this.technicalRequest?.unsubscribe();
      this.technical.set(null);
      this.technicalLoading.set(false);
      this.technicalError.set('');
      this.section.set('review');
    });
  }

  protected showTechnical(): void {
    this.section.set('technical');
    if (!this.technical()) {
      this.loadTechnical();
    }
  }

  protected loadTechnical(): void {
    if (this.technicalLoading()) {
      return;
    }
    const id = this.document().id;
    this.technicalLoading.set(true);
    this.technicalError.set('');
    this.technicalRequest = this.service
      .technical(id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (details): void => {
          this.technical.set(details);
          this.technicalLoading.set(false);
        },
        error: (error: unknown): void => {
          this.technicalError.set(apiError(error, 'Could not load saved technical details.'));
          this.technicalLoading.set(false);
        },
      });
  }
  protected readonly findingCount = computed(
    () =>
      this.document()
        .review?.passes.at(-1)
        ?.analysis.findings.filter((finding) => finding.severity !== 'suggestion').length ?? 0,
  );
  private readonly pendingFindingCount = computed((): number => {
    const pass = this.document().review?.passes.at(-1);
    const acknowledged = new Set(pass?.acknowledged_finding_indices ?? []);
    return (
      pass?.analysis.findings.filter(
        (finding, index) => finding.severity !== 'suggestion' && !acknowledged.has(index),
      ).length ?? 0
    );
  });
  protected readonly statusNote = computed((): string => {
    const status = this.document().status;
    if (status === 'awaiting_review') {
      return 'Waiting for your decision';
    }
    if (status === 'running') {
      return 'In progress';
    }
    if (status === 'failed') {
      return 'Needs attention';
    }
    if (status === 'cancelled') {
      return 'Cancelled';
    }
    if (!this.document().review) {
      return '';
    }
    const count = this.findingCount();
    return count
      ? `${String(count)} ${count === 1 ? 'finding' : 'findings'} to check`
      : 'No findings';
  });
  protected readonly canDecide = computed((): boolean => {
    const document = this.document();
    const review = document.review;
    return (
      !!review &&
      document.status !== 'running' &&
      this.pendingFindingCount() > 0 &&
      (review.status === 'awaiting_decision' ||
        review.status === 'failed' ||
        (review.status === 'needs_attention' && (review.decisions?.length ?? 0) === 0))
    );
  });
  protected readonly failureExplanation = computed((): string => {
    const error = this.document().error ?? '';
    if (error.includes('AI skill ranking')) {
      return 'The model returned an incomplete or repeated skill order. Your previous documents are saved. Continue from the review below when available, or start a new version; skill ordering is now repaired automatically.';
    }
    return error.split(' Review its progress and saved reports;')[0] ?? '';
  });

  protected resolve(decision: ReviewDecision): void {
    if (this.saving()) {
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.service
      .reviewApplication(this.document().id, decision)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.saving.set(false);
          this.updated.emit(document);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(
            apiError(error, 'Could not save your choices. They are still shown here.'),
          );
        },
      });
  }

  protected reload(): void {
    if (this.saving()) {
      return;
    }
    this.saving.set(true);
    this.service
      .get(this.document().id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.saving.set(false);
          this.error.set('');
          this.updated.emit(document);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(apiError(error, 'Could not reload saved progress.'));
        },
      });
  }
}
