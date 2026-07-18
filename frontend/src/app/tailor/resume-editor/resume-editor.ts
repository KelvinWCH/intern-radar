import { DOCUMENT, DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import type { Subscription } from 'rxjs';
import { finalize } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { BulletEditor } from '../bullet-editor/bullet-editor';
import { previewDelayMs, resumeLockedReasons } from '../constants/resume-editor.constants';
import { DocumentActions } from '../document-actions/document-actions';
import { DocumentsService } from '../documents.service';
import { EntryTools } from '../entry-tools/entry-tools';
import type { DocumentDetail } from '../models/document.models';
import type {
  BulletLayout,
  FittedLine,
  ResumeDraft,
  ShownPreview,
} from '../models/resume-editor.models';
import type { GeneratedResume } from '../models/resume.models';
import {
  bulletLayouts,
  canEditResume,
  draftIssues,
  draftResume,
  fittedKey,
  fittedLines,
  newEducation,
  newExperience,
  newProject,
  resumeDraft,
  resumeKey,
  savedResume,
  splitList,
} from '../resume-draft';

interface FitStatus {
  readonly state: 'fits' | 'over' | 'pending';
  readonly label: string;
}

@Component({
  selector: 'app-resume-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BulletEditor, DatePipe, DocumentActions, EntryTools, FormsModule, RouterLink],
  templateUrl: './resume-editor.html',
  styleUrl: './resume-editor.scss',
  host: { '(window:beforeunload)': 'warnBeforeUnload($event)' },
})
export class ResumeEditor {
  private readonly service = inject(DocumentsService);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly destroyRef = inject(DestroyRef);
  private readonly view = inject(DOCUMENT).defaultView;
  protected id = '';
  protected readonly document = signal<DocumentDetail | null>(null);
  protected readonly backLink = computed((): string[] => {
    const document = this.document();
    return document ? ['/jobs', document.job_id] : ['/documents', this.id];
  });
  protected readonly loadError = signal('');
  protected readonly draft = signal<ResumeDraft | null>(null);
  private base: GeneratedResume | null = null;
  private savedKey = '';
  protected readonly dirty = signal(false);
  protected readonly issues = signal<readonly string[]>([]);
  protected readonly saving = signal(false);
  protected readonly saveError = signal('');
  protected readonly message = signal('');
  protected readonly shown = signal<ShownPreview | null>(null);
  protected readonly previewing = signal(false);
  protected readonly previewError = signal('');
  protected readonly previewBehind = signal(false);
  private previewTimer: ReturnType<typeof setTimeout> | undefined;
  private previewRequest: Subscription | null = null;
  private previewAgain = false;
  protected readonly newEducation = newEducation;
  protected readonly newExperience = newExperience;
  protected readonly newProject = newProject;
  protected readonly editable = computed((): boolean => {
    const document = this.document();
    return document !== null && canEditResume(document);
  });
  protected readonly lockedReason = computed(
    (): string =>
      resumeLockedReasons[this.document()?.status ?? ''] ?? 'This attempt has no resume to edit.',
  );
  protected readonly previewUrl = computed((): SafeResourceUrl | null => {
    const url = this.shown()?.url;
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(`${url}#view=FitH`) : null;
  });
  protected readonly layouts = computed((): ReadonlyMap<string, BulletLayout> => {
    const shown = this.shown();
    return shown ? bulletLayouts(shown.resume, shown.preview) : new Map<string, BulletLayout>();
  });
  private readonly fitted = computed((): ReadonlyMap<string, FittedLine> => {
    const shown = this.shown();
    return shown ? fittedLines(shown.resume, shown.preview) : new Map<string, FittedLine>();
  });
  protected readonly fit = computed((): FitStatus | null => {
    if (this.previewing()) {
      return { state: 'pending', label: 'Updating the preview...' };
    }
    const shown = this.shown();
    if (!shown || this.previewError()) {
      return null;
    }
    if (this.previewBehind()) {
      return { state: 'pending', label: 'The preview catches up when you pause typing' };
    }
    const { page_count: pages, overflow_lines: lines, blank_inches: blank } = shown.preview;
    if (pages === 1) {
      return {
        state: 'fits',
        label:
          blank > 0
            ? `Fits on one page with ${blank.toFixed(1)} in. left at the bottom`
            : 'Fits on one page',
      };
    }
    return {
      state: 'over',
      label: `${
        lines
          ? `Runs about ${String(lines)} line${lines === 1 ? '' : 's'} past one page`
          : `Runs onto ${String(pages)} pages`
      }. Shorten something to save`,
    };
  });

  constructor() {
    inject(ActivatedRoute)
      .paramMap.pipe(takeUntilDestroyed())
      .subscribe((params): void => {
        this.id = params.get('id') ?? '';
        this.load();
      });
    this.destroyRef.onDestroy((): void => {
      this.clearPreview();
    });
  }

  canLeave(): boolean {
    return !this.dirty() || (this.view?.confirm('Leave without saving your resume edits?') ?? true);
  }

  protected warnBeforeUnload(event: Event): void {
    if (this.dirty()) {
      event.preventDefault();
    }
  }

  protected load(): void {
    this.loadError.set('');
    this.document.set(null);
    this.draft.set(null);
    this.base = null;
    this.dirty.set(false);
    this.issues.set([]);
    this.clearPreview();
    this.service
      .get(this.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (document): void => {
          this.document.set(document);
          this.open(document);
        },
        error: (error: unknown): void => {
          this.loadError.set(apiError(error, 'Could not load this resume.'));
        },
      });
  }

  protected changed(): void {
    const draft = this.draft();
    if (!draft || !this.base) {
      return;
    }
    this.message.set('');
    this.issues.set(draftIssues(draft));
    this.dirty.set(this.draftKey() !== this.savedKey);
    this.previewBehind.set(true);
    clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(
      (): void => {
        this.refreshPreview();
      },
      this.shown() ? previewDelayMs : 0,
    );
  }

  protected add<Item>(items: Item[], item: Item): void {
    items.push(item);
    this.changed();
  }

  protected printedNote(section: 'projects' | 'education', entry: number, text: string): string {
    const items = splitList(text);
    const line = this.fitted().get(fittedKey(section, entry, items));
    if (!line || line.printed >= items.length) {
      return '';
    }
    return (
      `Only the first ${String(line.printed)} of ${String(items.length)} fit on one line; ` +
      'saving keeps those, so put the most relevant first.'
    );
  }

  protected refreshPreview(): void {
    clearTimeout(this.previewTimer);
    const draft = this.draft();
    if (!draft || !this.base) {
      return;
    }
    if (this.previewRequest && !this.previewRequest.closed) {
      this.previewAgain = true;
      return;
    }
    if (draftIssues(draft).length) {
      this.previewError.set('Fill in the fields listed under Save to update the preview.');
      return;
    }
    const resume = draftResume(draft, this.base);
    const key = resumeKey(resume);
    if (key === this.shown()?.key) {
      this.previewBehind.set(false);
      this.previewError.set('');
      return;
    }
    this.previewing.set(true);
    this.previewError.set('');
    this.previewRequest = this.service
      .previewResume(resume)
      .pipe(
        finalize((): void => {
          this.previewRequest = null;
          this.previewing.set(false);
          if (this.previewAgain) {
            this.previewAgain = false;
            this.refreshPreview();
          }
        }),
      )
      .subscribe({
        next: (preview): void => {
          const previous = this.shown()?.url;
          if (previous) {
            URL.revokeObjectURL(previous);
          }
          this.shown.set({ resume, key, preview, url: URL.createObjectURL(preview.pdf) });
          this.previewBehind.set(this.draftKey() !== key);
        },
        error: (error: unknown): void => {
          this.previewError.set(
            apiError(error, 'Could not build the preview. Your edits are still here.'),
          );
        },
      });
  }

  protected save(): void {
    const document = this.document();
    const draft = this.draft();
    if (!document || !draft || !this.base || this.saving()) {
      return;
    }
    const issues = draftIssues(draft);
    this.issues.set(issues);
    if (issues.length) {
      return;
    }
    this.saving.set(true);
    this.saveError.set('');
    this.message.set('');
    this.service
      .saveResume(document.id, document.resume_revision ?? 0, draftResume(draft, this.base))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (saved): void => {
          this.saving.set(false);
          this.document.set(saved);
          this.open(saved);
          this.message.set(
            saved.resume_edited_at != null
              ? 'Saved. Downloads and the application package now use your edits.'
              : 'Saved. The resume is back to the version tailoring wrote.',
          );
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.saveError.set(
            apiError(error, 'Could not save your edits. They are still here; try again.'),
          );
        },
      });
  }

  protected discard(): void {
    const document = this.document();
    const saved = document ? savedResume(document) : null;
    if (saved) {
      this.fill(saved);
    }
  }

  protected startFromGenerated(): void {
    const generated = this.document()?.generated_resume;
    if (!generated) {
      return;
    }
    this.fill(generated);
    this.message.set('The generated version is loaded. Save to restore it, or keep editing.');
  }

  private open(document: DocumentDetail): void {
    const saved = savedResume(document);
    if (!saved || !canEditResume(document)) {
      return;
    }
    this.savedKey = resumeKey(draftResume(resumeDraft(saved), saved));
    this.fill(saved);
  }

  private fill(resume: GeneratedResume): void {
    this.base = resume;
    this.draft.set(resumeDraft(resume));
    this.changed();
  }

  private clearPreview(): void {
    clearTimeout(this.previewTimer);
    this.previewAgain = false;
    this.previewRequest?.unsubscribe();
    const url = this.shown()?.url;
    if (url) {
      URL.revokeObjectURL(url);
    }
    this.shown.set(null);
    this.previewError.set('');
    this.previewBehind.set(false);
  }

  private draftKey(): string {
    const draft = this.draft();
    return draft && this.base ? resumeKey(draftResume(draft, this.base)) : '';
  }
}
