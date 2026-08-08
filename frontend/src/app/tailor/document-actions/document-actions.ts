import {
  Component,
  DestroyRef,
  booleanAttribute,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { apiError } from '../../shared/api-error';
import { DocumentsService } from '../documents.service';
@Component({
  selector: 'app-document-actions',
  template: `@if (compact()) {
      <div class="compact">
        <button type="button" class="text-button" [disabled]="busy()" (click)="download('pdf')">
          {{ busy() === 'pdf' ? 'Preparing...' : 'PDF' }}</button
        ><button type="button" class="text-button" [disabled]="busy()" (click)="download('tex')">
          {{ busy() === 'tex' ? 'Preparing...' : '.tex' }}
        </button>
      </div>
    } @else {
      <div>
        <button
          type="button"
          [class]="draft() ? 'button-secondary' : 'button-primary'"
          [disabled]="busy()"
          (click)="download('pdf')"
        >
          <i class="pi pi-download"></i
          >{{
            busy() === 'pdf' ? 'Preparing PDF...' : draft() ? 'Download draft PDF' : 'Download PDF'
          }}</button
        ><button
          type="button"
          class="button-secondary"
          [disabled]="busy()"
          (click)="download('tex')"
        >
          {{ busy() === 'tex' ? 'Preparing...' : 'LaTeX (.tex)' }}
        </button>
      </div>
    }
    @if (error()) {
      <p>{{ error() }}</p>
    }`,
  styles: `
    div {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .compact {
      gap: 2px;
      flex-wrap: nowrap;
    }
    p {
      color: var(--accent);
      font-size: 12px;
      line-height: 1.6;
    }
  `,
})
export class DocumentActions {
  readonly documentId = input.required<string>();
  readonly kind = input.required<'resume' | 'cover-letter'>();
  readonly draft = input(false);
  readonly compact = input(false, { transform: booleanAttribute });
  protected readonly label = computed((): string =>
    this.kind() === 'resume' ? 'resume' : 'cover letter',
  );
  private readonly service = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly urls = new Map<string, string>();
  protected readonly busy = signal<'pdf' | 'tex' | null>(null);
  protected readonly error = signal('');
  constructor() {
    this.destroyRef.onDestroy((): void => {
      for (const url of this.urls.values()) {
        URL.revokeObjectURL(url);
      }
    });
  }
  protected download(format: 'pdf' | 'tex'): void {
    if (this.busy()) {
      return;
    }
    const key = `${this.documentId()}/${this.draft() ? 'draft/' : ''}${this.kind()}/${format}`;
    this.busy.set(format);
    this.error.set('');
    this.service
      .download(this.documentId(), this.kind(), format, this.draft())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ blob, filename }): void => {
          const previous = this.urls.get(key);
          if (previous) {
            URL.revokeObjectURL(previous);
          }
          const url = URL.createObjectURL(blob);
          this.urls.set(key, url);
          this.busy.set(null);
          this.saveFile(url, filename);
        },
        error: (error: unknown): void => {
          this.busy.set(null);
          this.error.set(
            apiError(
              error,
              'Could not prepare the download. Your saved document is unchanged; try again.',
            ),
          );
        },
      });
  }
  private saveFile(url: string, filename: string): void {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
  }
}
