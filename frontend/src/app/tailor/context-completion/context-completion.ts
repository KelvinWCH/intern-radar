import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { map, type Subscription } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { validAiOptions } from '../../shared/models/ai.models';
import { completionDelayMs } from '../constants/context-completion.constants';
import type { CompletionContext } from '../models/context-completion.models';
import { parseContextCompletion } from '../models/context-completion.models';
import { AiDefaults } from '../../settings/ai-defaults';

@Component({
  selector: 'app-context-completion',
  templateUrl: './context-completion.html',
  styleUrl: './context-completion.scss',
})
export class ContextCompletion {
  readonly textarea = input.required<HTMLTextAreaElement>();
  readonly context = input.required<CompletionContext>();
  readonly disabled = input(false);
  protected readonly suggestion = signal('');
  protected readonly model = signal('');
  protected readonly busy = signal(false);
  protected readonly enabled = signal(true);
  protected readonly message = signal('');
  private readonly http = inject(HttpClient);
  private readonly preferences = inject(AiDefaults);
  private readonly document = inject(DOCUMENT);
  private timer: ReturnType<typeof setTimeout> | undefined;
  private request: Subscription | undefined;
  private prefix = '';
  private lastRequestKey = '';
  private composing = false;
  private accepting = false;
  private acceptedText: string | null = null;
  private revision = 0;

  constructor() {
    effect((cleanup): void => {
      const target = this.textarea();
      this.context();
      this.disabled();
      this.enabled();
      const schedule = (): void => {
        if (!this.accepting) {
          this.schedule();
        }
      };
      const clear = (): void => {
        this.cancel();
      };
      const select = (): void => {
        if (!this.eligible()) {
          this.cancel();
        }
      };
      const start = (): void => {
        this.composing = true;
        this.cancel();
      };
      const end = (): void => {
        this.composing = false;
        this.schedule();
      };
      const key = (event: KeyboardEvent): void => {
        if (event.key === 'Escape') {
          this.cancel();
        }
        if (
          event.key === 'Tab' &&
          !event.shiftKey &&
          !event.ctrlKey &&
          !event.metaKey &&
          !event.altKey &&
          !event.isComposing &&
          this.canAccept()
        ) {
          event.preventDefault();
          this.accept();
        }
      };
      target.addEventListener('input', schedule);
      target.addEventListener('focus', schedule);
      target.addEventListener('blur', clear);
      target.addEventListener('click', select);
      target.addEventListener('keydown', key);
      target.addEventListener('compositionstart', start);
      target.addEventListener('compositionend', end);
      this.document.addEventListener('selectionchange', select);
      untracked((): void => {
        this.schedule();
      });
      cleanup((): void => {
        this.cancel();
        target.removeEventListener('input', schedule);
        target.removeEventListener('focus', schedule);
        target.removeEventListener('blur', clear);
        target.removeEventListener('click', select);
        target.removeEventListener('keydown', key);
        target.removeEventListener('compositionstart', start);
        target.removeEventListener('compositionend', end);
        this.document.removeEventListener('selectionchange', select);
      });
    });
  }

  protected accept(): void {
    if (!this.canAccept()) {
      return;
    }
    const target = this.textarea();
    const suffix = this.suggestion();
    this.cancel();
    this.accepting = true;
    target.setRangeText(suffix, target.value.length, target.value.length, 'end');
    target.dispatchEvent(new Event('input', { bubbles: true }));
    this.accepting = false;
    this.acceptedText = target.value;
    this.lastRequestKey = JSON.stringify({ ...this.context(), text: target.value });
    this.message.set('Suggestion added. You can edit it.');
  }

  protected dismiss(): void {
    this.cancel();
  }

  protected toggle(): void {
    this.enabled.update((value) => !value);
    this.lastRequestKey = '';
    this.cancel();
    this.textarea().focus();
  }

  protected retry(): void {
    this.lastRequestKey = '';
    this.acceptedText = null;
    this.textarea().focus();
    this.schedule();
  }

  private eligible(): boolean {
    const target = this.textarea();
    return (
      this.enabled() &&
      !this.disabled() &&
      !this.composing &&
      !target.matches(':disabled') &&
      !target.readOnly &&
      this.document.activeElement === target &&
      target.selectionStart === target.value.length &&
      target.selectionEnd === target.value.length
    );
  }

  private canAccept(): boolean {
    const target = this.textarea();
    return (
      !!this.suggestion() &&
      this.eligible() &&
      target.value === this.prefix &&
      (target.maxLength < 0 || target.value.length + this.suggestion().length <= target.maxLength)
    );
  }

  private cancel(): void {
    this.revision++;
    clearTimeout(this.timer);
    if (this.request && !this.request.closed) {
      this.lastRequestKey = '';
    }
    this.request?.unsubscribe();
    this.request = undefined;
    this.suggestion.set('');
    this.busy.set(false);
  }

  private schedule(): void {
    this.cancel();
    this.message.set('');
    if (!this.eligible()) {
      return;
    }
    const target = this.textarea();
    const context = this.context();
    if (target.value === this.acceptedText) {
      return;
    }
    if (
      !validAiOptions(context.ai_options ?? {}) ||
      (context.purpose === 'question' && target.value.trim().length < 3) ||
      (target.maxLength >= 0 && target.value.length >= target.maxLength)
    ) {
      return;
    }
    const body = {
      ...context,
      text: target.value,
      ai_options: { ...context.ai_options, ...this.preferences.options('completion') },
    };
    const key = JSON.stringify(body);
    if (this.lastRequestKey === key) {
      return;
    }
    const revision = this.revision;
    this.timer = setTimeout((): void => {
      if (!this.eligible() || this.revision !== revision || target.value !== body.text) {
        return;
      }
      this.lastRequestKey = key;
      this.prefix = body.text;
      this.busy.set(true);
      this.request = this.http
        .post<unknown>('/api/resumes/questions/complete', body)
        .pipe(map(parseContextCompletion))
        .subscribe({
          next: (result): void => {
            this.busy.set(false);
            if (revision !== this.revision || !this.eligible() || target.value !== body.text) {
              return;
            }
            if (
              result.continuation &&
              (target.maxLength < 0 ||
                body.text.length + result.continuation.length <= target.maxLength)
            ) {
              this.suggestion.set(result.continuation);
              this.model.set(result.model);
            } else {
              this.message.set('No supported suggestion. Add the details in your own words.');
            }
          },
          error: (error: unknown): void => {
            this.busy.set(false);
            this.message.set(apiError(error, 'Suggestion unavailable. Keep typing or try again.'));
          },
        });
    }, completionDelayMs);
  }
}
