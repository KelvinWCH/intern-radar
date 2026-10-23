import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { apiError } from '../../shared/api-error';
import { saveFile } from '../../shared/save-file';
import { TranscriptService, transcriptMaxBytes } from '../transcript.service';

@Component({
  selector: 'app-transcript-card',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './transcript-card.html',
  styleUrl: './transcript-card.scss',
})
export class TranscriptCard {
  private readonly service = inject(TranscriptService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly transcript = this.service.transcript;
  protected readonly busy = signal<'upload' | 'download' | 'remove' | null>(null);
  protected readonly error = signal('');

  constructor() {
    this.service
      .load()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        error: (error: unknown): void => {
          this.error.set(apiError(error, 'Could not check for a saved transcript.'));
        },
      });
  }

  protected upload(input: HTMLInputElement): void {
    const file = input.files?.[0];
    input.value = '';
    if (!file || this.busy()) {
      return;
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      this.error.set('Choose a PDF. Most schools let you save or print the transcript as one.');
      return;
    }
    if (file.size > transcriptMaxBytes) {
      this.error.set('That PDF is over 5 MB. Export a smaller copy and try again.');
      return;
    }
    this.run('upload', this.service.upload(file), 'Could not save the transcript. Try again.');
  }

  protected download(): void {
    if (this.busy()) {
      return;
    }
    this.busy.set('download');
    this.error.set('');
    this.service
      .download()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ blob, filename }): void => {
          this.busy.set(null);
          saveFile(blob, filename);
        },
        error: (error: unknown): void => {
          this.busy.set(null);
          this.error.set(apiError(error, 'Could not download the transcript. Try again.'));
        },
      });
  }

  protected remove(): void {
    if (this.busy() || !confirm('Remove your saved transcript?')) {
      return;
    }
    this.run('remove', this.service.remove(), 'Could not remove the transcript. Try again.');
  }

  private run(
    action: 'upload' | 'remove',
    request: ReturnType<TranscriptService['remove']>,
    fallback: string,
  ): void {
    this.busy.set(action);
    this.error.set('');
    request.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (): void => {
        this.busy.set(null);
      },
      error: (error: unknown): void => {
        this.busy.set(null);
        this.error.set(apiError(error, fallback));
      },
    });
  }
}
