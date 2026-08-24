import { Component, DestroyRef, computed, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../shared/api-error';
import { DocumentsService } from '../documents.service';
import type { DocumentDetail } from '../models/document.models';
import type {
  ResearchAnalysis,
  ResearchFinding,
  ResearchReviewRequest,
} from '../models/research.models';

@Component({
  selector: 'app-research-review',
  imports: [FormsModule],
  templateUrl: './research-review.html',
  styleUrl: './research-review.scss',
})
export class ResearchReview {
  readonly document = input.required<DocumentDetail>();
  readonly updated = output<DocumentDetail>();
  private readonly service = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly draft = signal<ResearchAnalysis | null>(null);
  protected readonly customPrompt = signal<string | null>(null);
  protected readonly researchPrompt = computed((): string => {
    const document = this.document();
    const savedPrompt = document.research?.research_prompt;
    return (
      this.customPrompt() ??
      (savedPrompt?.trim()
        ? savedPrompt
        : `Research what a ${document.title} at ${document.company} typically does. ` +
          `Cover the company's work, typical responsibilities, relevant skills and tools, ` +
          `example projects, and experience to highlight in an application. Separate verified ` +
          `company facts from general role expectations and note what is unknown about this specific opening.`)
    );
  });
  protected readonly missingRoleDetails = computed((): boolean => {
    const report = this.document().research;
    return (
      !!report &&
      report.mode !== 'generic' &&
      !report.analysis.role_priorities.length &&
      !report.analysis.requirements.length &&
      !report.analysis.preferred_qualifications.length
    );
  });
  private draftRevision = 1;
  protected readonly reviewable = computed((): boolean => {
    const document = this.document();
    return (
      !!document.research &&
      !document.review &&
      (document.status === 'awaiting_review' ||
        (document.status === 'failed' &&
          !document.has_resume &&
          !document.has_cover_letter &&
          !!document.error?.includes('Research citation does not belong to its stated source')))
    );
  });
  protected guidance = '';
  protected unknowns = '';
  protected generalGuidance = '';
  protected companyKnowledge = '';

  protected edit(): void {
    const analysis = this.document().research?.analysis;
    if (!analysis) {
      return;
    }
    this.draftRevision = this.document().research?.revision ?? 1;
    this.draft.set(structuredClone(analysis));
    this.guidance = analysis.tailoring_guidance.join('\n');
    this.unknowns = analysis.unknowns.join('\n');
    this.generalGuidance = analysis.general_role_guidance.join('\n');
    this.companyKnowledge = analysis.company_knowledge.join('\n');
    this.error.set('');
  }

  protected newFinding(): ResearchFinding {
    return { finding: '', source_index: 0, quote: '' };
  }

  protected submit(action: ResearchReviewRequest['action']): void {
    const report = this.document().research;
    if (!report || this.saving()) {
      return;
    }
    const draft = this.draft();
    if (action !== 'save' && draft) {
      return;
    }
    if (
      action === 'generate_generic' &&
      (!this.researchPrompt().trim() || this.researchPrompt().length > 2000)
    ) {
      return;
    }
    if (draft) {
      draft.tailoring_guidance = this.guidance
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      draft.unknowns = this.unknowns
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      draft.general_role_guidance = this.generalGuidance
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      draft.company_knowledge = this.companyKnowledge
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
    }
    this.saving.set(true);
    this.error.set('');
    this.service
      .reviewResearch(this.document().id, {
        action,
        revision: draft ? this.draftRevision : report.revision,
        ...(draft ? { analysis: draft } : {}),
        ...(action === 'generate_generic' ? { research_prompt: this.researchPrompt().trim() } : {}),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.saving.set(false);
          this.draft.set(null);
          this.updated.emit(document);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(
            apiError(
              error,
              'Could not start or save this research. Your prompt and edits are still here.',
            ),
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
          this.draft.set(null);
          this.updated.emit(document);
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(
            apiError(error, 'Could not reload the saved report. Your edits are still here.'),
          );
        },
      });
  }
}
