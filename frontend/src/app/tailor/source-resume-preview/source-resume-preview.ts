import { HttpErrorResponse } from '@angular/common/http';
import type { ElementRef } from '@angular/core';
import { Component, DestroyRef, computed, inject, input, signal, viewChild } from '@angular/core';
import type { SafeResourceUrl } from '@angular/platform-browser';
import { DomSanitizer } from '@angular/platform-browser';
import type { Subscription } from 'rxjs';
import type { ResumeProfile } from '../models/resume.models';
import { ResumeService } from '../resume.service';

@Component({
  selector: 'app-source-resume-preview',
  templateUrl: './source-resume-preview.html',
  styleUrl: './source-resume-preview.scss',
})
export class SourceResumePreview {
  readonly profile = input.required<ResumeProfile>();
  private readonly service = inject(ResumeService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('previewDialog');
  private request: Subscription | null = null;
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly downloadUrl = signal<string | null>(null);
  protected readonly previewUrl = computed((): SafeResourceUrl | null => {
    const url = this.downloadUrl();
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  });

  constructor() {
    inject(DestroyRef).onDestroy((): void => {
      this.clearPreview();
    });
  }

  protected open(): void {
    this.dialog().nativeElement.showModal();
    this.load();
  }

  protected load(): void {
    this.clearPreview();
    this.loading.set(true);
    this.request = this.service.sourcePdf().subscribe({
      next: (pdf): void => {
        this.downloadUrl.set(URL.createObjectURL(pdf));
        this.loading.set(false);
      },
      error: (error: unknown): void => {
        this.loading.set(false);
        this.error.set(this.describeError(error));
      },
    });
  }

  protected close(): void {
    this.dialog().nativeElement.close();
    this.clearPreview();
  }

  protected clearPreview(): void {
    this.request?.unsubscribe();
    this.request = null;
    const url = this.downloadUrl();
    if (url) {
      URL.revokeObjectURL(url);
    }
    this.downloadUrl.set(null);
    this.loading.set(false);
    this.error.set('');
  }

  private describeError(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      switch (error.status) {
        case 0:
          return 'Could not reach the backend. Check the connection and try again.';
        case 404:
          return 'The saved source resume is no longer available. Close this preview and upload a resume.';
        case 422:
          return 'The saved resume could not fit the PDF layout or preview limits. Your saved data has not changed.';
        case 503:
          return 'PDF preview is unavailable. Configure Tectonic on the backend, then try again. Your saved resume has not changed.';
      }
    }
    return 'Could not prepare the PDF preview. Your saved resume has not changed. Please try again.';
  }
}
