import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import {
  Component,
  DestroyRef,
  type ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import type { Subscription } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { DocumentsService } from '../documents.service';

export interface PdfPreviewRequest {
  readonly documentId: string;
  readonly kind: 'resume' | 'cover-letter';
  readonly title: string;
  readonly subtitle?: string;
  readonly draft?: boolean;
}

@Component({
  selector: 'app-pdf-preview-dialog',
  templateUrl: './pdf-preview-dialog.html',
  styleUrl: './pdf-preview-dialog.scss',
})
export class PdfPreviewDialog {
  private readonly service = inject(DocumentsService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('previewDialog');
  private request: Subscription | null = null;
  protected readonly current = signal<PdfPreviewRequest | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly filename = signal('');
  protected readonly downloadUrl = signal<string | null>(null);
  protected readonly previewUrl = computed((): SafeResourceUrl | null => {
    const url = this.downloadUrl();
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  });

  constructor() {
    inject(DestroyRef).onDestroy((): void => {
      this.clear();
    });
  }

  open(request: PdfPreviewRequest): void {
    this.current.set(request);
    this.dialog().nativeElement.showModal();
    this.load();
  }

  protected load(): void {
    const request = this.current();
    if (!request) {
      return;
    }
    this.clear();
    this.loading.set(true);
    this.request = this.service
      .download(request.documentId, request.kind, 'pdf', request.draft ?? false)
      .subscribe({
        next: ({ blob, filename }): void => {
          this.downloadUrl.set(URL.createObjectURL(blob));
          this.filename.set(filename);
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(
            apiError(
              error,
              'Could not prepare the PDF preview. Your saved document is unchanged; try again.',
            ),
          );
        },
      });
  }

  protected close(): void {
    this.dialog().nativeElement.close();
  }

  protected clear(): void {
    this.request?.unsubscribe();
    this.request = null;
    const url = this.downloadUrl();
    if (url) {
      URL.revokeObjectURL(url);
    }
    this.downloadUrl.set(null);
    this.filename.set('');
    this.loading.set(false);
    this.error.set('');
  }
}
