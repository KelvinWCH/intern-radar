import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { apiError } from '../../shared/api-error';
import { DocumentsService } from '../documents.service';
import type { DocumentDetail } from '../models/document.models';

type TailoringControl = 'pause' | 'resume' | 'cancel';

@Component({
  selector: 'app-tailoring-controls',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './tailoring-controls.html',
  styleUrl: './tailoring-controls.scss',
})
export class TailoringControls {
  readonly document = input.required<DocumentDetail>();
  readonly changed = output<DocumentDetail>();
  private readonly documents = inject(DocumentsService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly paused = computed((): boolean => this.document().paused_at != null);
  protected readonly held = computed((): boolean => {
    let pauses = 0;
    for (const event of [...(this.document().events ?? [])].reverse()) {
      if (event.stage === 'resumed') {
        break;
      }
      if (event.stage === 'paused') {
        pauses += 1;
      }
    }
    return pauses > 1;
  });
  protected readonly busy = signal<TailoringControl | null>(null);
  protected readonly confirming = signal(false);
  protected readonly error = signal('');

  protected send(action: TailoringControl): void {
    if (this.busy()) {
      return;
    }
    this.busy.set(action);
    this.error.set('');
    this.documents
      .control(this.document().id, action)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.busy.set(null);
          this.confirming.set(false);
          this.changed.emit(document);
        },
        error: (error: unknown): void => {
          this.busy.set(null);
          this.error.set(apiError(error, 'Could not change tailoring. Refresh and try again.'));
        },
      });
  }
}
