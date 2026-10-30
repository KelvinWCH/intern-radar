import { Injectable, inject, signal } from '@angular/core';
import type { DocumentSummary } from '../../jobs/models/user-data.models';
import { apiError } from '../../shared/api-error';
import { requestId } from '../../shared/request-id';
import { oneShotDefaults } from '../constants/tailoring-mode.constants';
import { DocumentsService } from '../documents.service';
import type { TailorRequest } from '../models/document.models';
import type { QuickGenerateJob, QuickGenerateState } from '../models/quick-generate.models';

const idle: QuickGenerateState = { status: 'idle' };
const pollMilliseconds = 5000;

function quickRequest(): TailorRequest {
  return {
    request_id: requestId(),
    mode: 'one_shot',
    one_shot_ai_options: { ...oneShotDefaults },
    include_resume: true,
    include_cover_letter: true,
  };
}

@Injectable({ providedIn: 'root' })
export class QuickGenerateStore {
  private readonly documents = inject(DocumentsService);
  private readonly runs = signal<ReadonlyMap<string, QuickGenerateState>>(new Map());
  private timer: ReturnType<typeof setInterval> | null = null;

  state(jobId: string): QuickGenerateState {
    return this.runs().get(jobId) ?? idle;
  }

  start(job: QuickGenerateJob): void {
    const status = this.state(job.id).status;
    if (status === 'starting' || status === 'running') {
      return;
    }
    this.set(job.id, { status: 'starting' });
    this.documents.start(job.id, quickRequest()).subscribe({
      next: (document): void => {
        this.record(job.id, document);
      },
      error: (error: unknown): void => {
        this.set(job.id, {
          status: 'failed',
          documentId: null,
          error: apiError(error, 'Could not start quick generation. Try again.'),
        });
      },
    });
  }

  // check running documents every few seconds until they finish
  private check(): void {
    let running = false;
    for (const [jobId, run] of this.runs()) {
      if (run.status !== 'running') {
        continue;
      }
      running = true;
      this.documents.get(run.documentId).subscribe({
        next: (document): void => {
          const current = this.runs().get(jobId);
          if (current?.status === 'running' && current.documentId === document.id) {
            this.record(jobId, document);
          }
        },
        error: (): void => undefined,
      });
    }
    if (!running && this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private record(jobId: string, document: DocumentSummary): void {
    if (document.status === 'running') {
      this.set(jobId, { status: 'running', documentId: document.id });
      this.timer ??= setInterval((): void => {
        this.check();
      }, pollMilliseconds);
    } else if (document.status === 'cancelled') {
      this.set(jobId, idle);
    } else if (document.status === 'failed') {
      this.set(jobId, {
        status: 'failed',
        documentId: document.id,
        error: document.error ?? 'Generation failed. Open the attempt for details.',
      });
    } else {
      this.set(jobId, { status: 'ready', documentId: document.id });
    }
  }

  private set(jobId: string, state: QuickGenerateState): void {
    this.runs.update((runs): ReadonlyMap<string, QuickGenerateState> => {
      const next = new Map(runs);
      if (state.status === 'idle') {
        next.delete(jobId);
      } else {
        next.set(jobId, state);
      }
      return next;
    });
  }
}
