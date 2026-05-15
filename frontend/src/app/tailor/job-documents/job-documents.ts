import { DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { CheckboxModule } from 'primeng/checkbox';
import type { Subscription } from 'rxjs';
import type { DocumentSummary } from '../../jobs/models/user-data.models';
import { TranscriptService } from '../../resume-manager/transcript.service';
import { AiUsageSummary } from '../../shared/ai-usage-summary';
import { apiError } from '../../shared/api-error';
import { relativeTime } from '../../shared/relative-time';
import { saveFile } from '../../shared/save-file';
import { documentStatusLabels, versionClockIntervalMs } from '../constants/job-documents.constants';
import { CoverLetterPreview } from '../cover-letter-preview/cover-letter-preview';
import { DocumentActions } from '../document-actions/document-actions';
import { DocumentsService } from '../documents.service';
import type { DocumentDetail } from '../models/document.models';
import type { DocumentVersion } from '../models/job-documents.models';
import { PdfPreviewDialog } from '../pdf-preview-dialog/pdf-preview-dialog';
import { pendingTailoringAttempt } from '../pending-attempt';
import { canEditResume } from '../resume-draft';
import { ResumePreview } from '../resume-preview/resume-preview';
import { TailoringConsole } from '../tailoring-console/tailoring-console';
import { TailoringReports } from '../tailoring-reports/tailoring-reports';
import { UnfittedDraftPanel } from '../unfitted-draft/unfitted-draft';

@Component({
  selector: 'app-job-documents',
  imports: [
    DatePipe,
    FormsModule,
    RouterLink,
    CheckboxModule,
    AiUsageSummary,
    CoverLetterPreview,
    DocumentActions,
    PdfPreviewDialog,
    ResumePreview,
    TailoringConsole,
    TailoringReports,
    UnfittedDraftPanel,
  ],
  templateUrl: './job-documents.html',
  styleUrl: './job-documents.scss',
})
export class JobDocuments {
  readonly company = input('');
  readonly title = input('');
  readonly documents = input<readonly DocumentSummary[]>([]);
  readonly live = input<DocumentDetail | null>(null);
  readonly liveWorking = input(false);
  readonly liveError = input('');
  readonly starting = input(false);
  readonly requestedVersion = input<string | null>(null);
  readonly liveChanged = output<DocumentDetail>();
  readonly liveUpdated = output<DocumentDetail>();
  readonly changed = output();
  private readonly service = inject(DocumentsService);
  private readonly transcripts = inject(TranscriptService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly chosen = signal<string | null>(null);
  private readonly loaded = signal<ReadonlyMap<string, DocumentDetail>>(new Map());
  private readonly now = signal(Date.now() / 1000);
  private request: Subscription | undefined;
  private readingId: string | null = null;
  private transcriptRequested = false;
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly canEditResume = canEditResume;
  protected readonly statusLabels = documentStatusLabels;
  protected readonly transcript = this.transcripts.transcript;
  protected readonly includeTranscript = signal(true);
  protected readonly transcriptBusy = signal(false);
  protected readonly packageFormat = signal<'pdf' | 'zip'>('pdf');
  protected readonly packageBusy = signal(false);
  protected readonly packageError = signal('');
  protected readonly versions = computed((): readonly DocumentVersion[] => {
    const live = this.live();
    const loaded = this.loaded();
    const summaries = this.documents().map((document): DocumentSummary => {
      if (document.id === live?.id) {
        return live;
      }
      const read = loaded.get(document.id);
      return read?.status === document.status ? read : document;
    });
    const known = summaries.some((document): boolean => document.id === live?.id);
    const ordered = [...summaries, ...(live && !known ? [live] : [])].sort(
      (first, second): number => first.created_at - second.created_at,
    );
    let number = 0;
    const numbered = ordered.map((summary): DocumentVersion => {
      if (summary.status === 'completed') {
        number++;
      }
      return { summary, number: summary.status === 'completed' ? number : null, latest: false };
    });
    let latest: DocumentVersion | undefined;
    for (const version of numbered) {
      if (version.number !== null) {
        latest = version;
      }
    }
    return numbered
      .map((version): DocumentVersion =>
        version === latest ? { ...version, latest: true } : version,
      )
      .reverse();
  });
  protected readonly completedCount = computed(
    (): number => this.versions().filter((version): boolean => version.number !== null).length,
  );
  protected readonly selectedId = computed((): string | null => {
    const versions = this.versions();
    const chosen = this.chosen();
    if (chosen && versions.some((version): boolean => version.summary.id === chosen)) {
      return chosen;
    }
    const live = this.live();
    if (live) {
      return live.id;
    }
    const pending = pendingTailoringAttempt(this.documents());
    if (pending) {
      return pending.id;
    }
    return (
      versions.find((version): boolean => version.latest)?.summary.id ??
      versions[0]?.summary.id ??
      null
    );
  });
  protected readonly selected = computed(
    (): DocumentVersion | null =>
      this.versions().find((version): boolean => version.summary.id === this.selectedId()) ?? null,
  );
  protected readonly selectedIsLive = computed(
    (): boolean => !!this.live() && this.live()?.id === this.selectedId(),
  );
  protected readonly detail = computed((): DocumentDetail | null => {
    const id = this.selectedId();
    const live = this.live();
    if (live?.id === id) {
      return live;
    }
    return id ? (this.loaded().get(id) ?? null) : null;
  });
  protected readonly connecting = computed(
    (): boolean =>
      !this.detail() && this.selectedId() === pendingTailoringAttempt(this.documents())?.id,
  );
  protected readonly consoleShown = computed((): boolean => {
    if ((this.starting() && !this.live()) || this.connecting()) {
      return true;
    }
    const detail = this.detail();
    return (
      !!detail &&
      (detail.status === 'running' ||
        detail.status === 'awaiting_review' ||
        (detail.events?.length ?? 0) > 0)
    );
  });
  protected readonly finished = computed((): boolean => {
    const status = this.detail()?.status;
    return status === 'completed' || status === 'failed' || status === 'cancelled';
  });
  protected readonly consolePending = computed(
    (): boolean => this.connecting() || (this.starting() && !this.live() && this.liveWorking()),
  );
  protected readonly consoleConnected = computed((): boolean => {
    const detail = this.detail();
    if (!detail) {
      return true;
    }
    return this.selectedIsLive()
      ? this.liveWorking() || detail.status !== 'running'
      : !this.error();
  });
  protected readonly consoleError = computed((): string =>
    this.selectedIsLive() || !this.detail() ? this.liveError() : '',
  );

  constructor() {
    const timer = setInterval((): void => {
      this.now.set(Date.now() / 1000);
    }, versionClockIntervalMs);
    this.destroyRef.onDestroy((): void => {
      clearInterval(timer);
      this.request?.unsubscribe();
    });
    effect((): void => {
      const requested = this.requestedVersion();
      if (requested) {
        untracked((): void => {
          this.chosen.set(requested);
        });
      }
    });
    effect((): void => {
      const live = this.live();
      const saved = this.documents().some((document): boolean => document.id === live?.id);
      if (live && !saved) {
        untracked((): void => {
          this.chosen.set(live.id);
        });
      }
    });
    effect((): void => {
      const id = this.selectedId();
      const liveId = this.live()?.id;
      const pendingId = pendingTailoringAttempt(this.documents())?.id;
      const summary = this.documents().find((document): boolean => document.id === id);
      const read = id ? this.loaded().get(id) : undefined;
      const current = !!read && (!summary || summary.status === read.status);
      untracked((): void => {
        if (!id || id === liveId || id === pendingId) {
          this.stopReading();
          return;
        }
        if (current || this.readingId === id) {
          return;
        }
        this.read(id);
      });
    });
    effect((): void => {
      if (!this.completedCount() || this.transcriptRequested) {
        return;
      }
      this.transcriptRequested = true;
      untracked((): void => {
        this.transcripts
          .load()
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe({
            error: (): void => {
              this.transcriptRequested = false;
            },
          });
      });
    });
  }

  protected select(id: string): void {
    this.chosen.set(id);
  }

  protected retry(): void {
    const id = this.selectedId();
    if (id) {
      this.read(id);
    }
  }

  protected consoleChanged(document: DocumentDetail): void {
    if (this.selectedIsLive()) {
      this.liveChanged.emit(document);
    } else {
      this.loadedChanged(document);
    }
  }

  protected loadedChanged(document: DocumentDetail): void {
    this.remember(document);
    if (document.status === 'running') {
      this.read(document.id, document);
    } else {
      this.changed.emit();
    }
  }

  protected ago(seconds: number, units = 2): string {
    return relativeTime(seconds, this.now(), units);
  }

  protected versionName(version: DocumentVersion): string {
    return version.number === null
      ? this.statusLabels[version.summary.status]
      : `Version ${String(version.number)}`;
  }

  protected contents(summary: DocumentSummary): string {
    const parts = [
      ...(summary.has_resume ? ['Resume'] : []),
      ...(summary.has_cover_letter ? ['Cover letter'] : []),
    ];
    return parts.length ? parts.join(' + ') : 'No documents';
  }

  protected duration(summary: DocumentSummary): string {
    if (summary.finished_at === null) {
      return '';
    }
    const seconds = Math.max(0, Math.round(summary.finished_at - summary.created_at));
    if (seconds < 60) {
      return `${String(seconds)} s`;
    }
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) {
      return `${String(minutes)} min`;
    }
    const rest = minutes % 60;
    return `${String(Math.floor(minutes / 60))} h${rest ? ` ${String(rest)} min` : ''}`;
  }

  protected packageSummary(saved: DocumentSummary): string {
    const parts = [
      ...(saved.has_cover_letter ? ['cover letter'] : []),
      ...(saved.has_resume ? ['resume'] : []),
      ...(this.transcript() && this.includeTranscript() ? ['transcript'] : []),
    ];
    const list =
      parts.length > 1
        ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1) ?? ''}`
        : (parts[0] ?? '');
    const sentence = `${list.charAt(0).toUpperCase()}${list.slice(1)}`;
    return this.packageFormat() === 'pdf'
      ? `${sentence} in one PDF`
      : `${sentence} as separate PDFs`;
  }

  protected downloadPackage(id: string): void {
    if (this.packageBusy()) {
      return;
    }
    this.packageBusy.set(true);
    this.packageError.set('');
    this.service
      .downloadPackage(id, this.packageFormat(), !!this.transcript() && this.includeTranscript())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ blob, filename }): void => {
          this.packageBusy.set(false);
          saveFile(blob, filename);
        },
        error: (error: unknown): void => {
          this.packageBusy.set(false);
          this.packageError.set(
            apiError(error, 'Could not prepare the download. Your documents are unchanged.'),
          );
        },
      });
  }

  protected downloadTranscript(): void {
    if (this.transcriptBusy()) {
      return;
    }
    this.transcriptBusy.set(true);
    this.packageError.set('');
    this.transcripts
      .download()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ blob, filename }): void => {
          this.transcriptBusy.set(false);
          saveFile(blob, filename);
        },
        error: (error: unknown): void => {
          this.transcriptBusy.set(false);
          this.packageError.set(apiError(error, 'Could not download the transcript.'));
        },
      });
  }

  private remember(document: DocumentDetail): void {
    this.loaded.update((versions): ReadonlyMap<string, DocumentDetail> =>
      new Map(versions).set(document.id, document),
    );
  }

  private stopReading(): void {
    this.request?.unsubscribe();
    this.readingId = null;
    this.loading.set(false);
  }

  private read(id: string, initial?: DocumentDetail): void {
    this.request?.unsubscribe();
    this.readingId = id;
    this.loading.set(!initial);
    this.error.set('');
    let wasRunning = initial?.status === 'running';
    this.request = this.service
      .watch(id, initial)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.loading.set(false);
          this.remember(document);
          if (wasRunning && document.status !== 'running') {
            this.changed.emit();
          }
          wasRunning = document.status === 'running';
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.readingId = null;
          this.error.set(apiError(error, 'Could not load this version.'));
        },
        complete: (): void => {
          this.readingId = null;
        },
      });
  }
}
