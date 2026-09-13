import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import type { Subscription } from 'rxjs';
import { PostedDate } from '../../jobs/posted-date/posted-date';
import { AiUsageSummary } from '../../shared/ai-usage-summary';
import { apiError } from '../../shared/api-error';
import { CursorNavigation } from '../../shared/pagination';
import { DocumentsService } from '../documents.service';
import { PdfPreviewDialog } from '../pdf-preview-dialog/pdf-preview-dialog';
import type { DocumentSummary } from '../../jobs/models/user-data.models';
import type { DocumentPage } from '../models/document.models';
@Component({
  selector: 'app-document-history',
  imports: [AiUsageSummary, DatePipe, TitleCasePipe, RouterLink, PostedDate, PdfPreviewDialog],
  templateUrl: './document-history.html',
  styles: `
    .nowrap {
      white-space: nowrap;
    }
    .role-link {
      font-weight: 500;
    }
    .workspace-page .data-table td .role-meta {
      margin: 2px 0 0;
    }
    .document-chips {
      display: flex;
      gap: 6px;
    }
    .document-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 9px;
      white-space: nowrap;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface);
      color: var(--accent);
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    .document-chip:hover {
      background: var(--accent-soft);
    }
  `,
})
export class DocumentHistory {
  private readonly service = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  private request: Subscription | undefined;
  private readonly pdfPreview = viewChild.required(PdfPreviewDialog);
  protected readonly navigation = new CursorNavigation();
  protected readonly page = signal<DocumentPage | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  constructor() {
    this.load();
  }

  protected preview(item: DocumentSummary, kind: 'resume' | 'cover-letter'): void {
    this.pdfPreview().open({
      documentId: item.id,
      kind,
      title: kind === 'resume' ? 'Tailored resume' : 'Cover letter',
      subtitle: `${item.company} · ${item.title}`,
    });
  }
  protected load(offset = 0): void {
    if (offset === 0) {
      this.navigation.reset();
    }
    const cursor = this.navigation.cursor(offset);
    if (cursor === undefined) {
      return;
    }
    this.request?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    this.request = this.service
      .history(offset, cursor)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page): void => {
          this.navigation.remember(page);
          this.page.set(page);
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not load document history.'));
        },
      });
  }
}
