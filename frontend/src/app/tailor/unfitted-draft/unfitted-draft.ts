import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CoverLetterPreview } from '../cover-letter-preview/cover-letter-preview';
import { DocumentActions } from '../document-actions/document-actions';
import type { CoverLetter, UnfittedDraft } from '../models/document.models';
import type { GeneratedResume } from '../models/resume.models';
import { ResumePreview } from '../resume-preview/resume-preview';

@Component({
  selector: 'app-unfitted-draft',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CoverLetterPreview, DocumentActions, ResumePreview, RouterLink],
  templateUrl: './unfitted-draft.html',
  styleUrl: './unfitted-draft.scss',
})
export class UnfittedDraftPanel {
  readonly documentId = input.required<string>();
  readonly resume = input<UnfittedDraft<GeneratedResume> | null>(null);
  readonly letter = input<UnfittedDraft<CoverLetter> | null>(null);
  readonly editable = input(false);
  protected readonly overflowLines = computed(
    (): number => (this.resume() ?? this.letter())?.overflow_lines ?? 0,
  );
}
