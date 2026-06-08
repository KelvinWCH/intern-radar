import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { apiError } from '../../shared/api-error';
import { DocumentsService } from '../documents.service';

@Component({
  selector: 'app-document-detail',
  imports: [RouterLink],
  template: `
    <div class="workspace-page">
      @if (error()) {
        <p class="notice error">{{ error() }}</p>
        <p class="actions">
          <button class="button-secondary" type="button" (click)="load()">Retry</button>
          <a class="button-secondary" routerLink="/documents">Every job's documents</a>
        </p>
      } @else {
        <p class="empty-state">
          <i class="pi pi-spinner pi-spin"></i> Opening the job's documents…
        </p>
      }
    </div>
  `,
  styles: `
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 12px 0 0;
    }
  `,
})
export class DocumentDetail {
  private readonly service = inject(DocumentsService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private id = '';
  protected readonly error = signal('');
  constructor() {
    inject(ActivatedRoute)
      .paramMap.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params): void => {
        this.id = params.get('id') ?? '';
        this.load();
      });
  }
  protected load(): void {
    this.error.set('');
    this.service
      .get(this.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          void this.router.navigate(['/jobs', document.job_id], {
            queryParams: { version: document.id },
            replaceUrl: true,
          });
        },
        error: (error: unknown): void => {
          this.error.set(apiError(error, 'Could not open these documents.'));
        },
      });
  }
}
