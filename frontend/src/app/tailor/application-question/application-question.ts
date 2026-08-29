import { Clipboard } from '@angular/cdk/clipboard';
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import type { JobSummary } from '../../jobs/models/job.models';
import { apiError } from '../../shared/api-error';
import { validAiOptions, type AiModelOptions } from '../../shared/models/ai.models';
import { AiOptions } from '../ai-options/ai-options';
import { ContextCompletion } from '../context-completion/context-completion';
import type { QuestionAnswer } from '../models/question.models';
import { QuestionService } from '../question.service';

@Component({
  selector: 'app-application-question',
  imports: [FormsModule, AiOptions, ContextCompletion],
  templateUrl: './application-question.html',
  styleUrl: './application-question.scss',
})
export class ApplicationQuestion {
  readonly job = input.required<JobSummary>();
  private readonly service = inject(QuestionService);
  private readonly clipboard = inject(Clipboard);
  private readonly destroyRef = inject(DestroyRef);
  protected question = '';
  protected context = '';
  protected maxWords: number | null = 200;
  protected draft = '';
  protected readonly busy = signal(false);
  protected readonly error = signal('');
  protected readonly copyMessage = signal('');
  protected readonly response = signal<QuestionAnswer | null>(null);
  protected readonly answerLimit = signal(200);
  protected readonly aiOptions = signal<AiModelOptions>({});
  protected readonly showModels = signal(false);
  protected readonly targetJob = computed(() => {
    const job = this.job();
    return (job.cleanedDescription ?? job.rawDescription)?.trim()
      ? {
          company: job.company,
          title: job.title,
          raw_description: job.cleanedDescription ?? job.rawDescription ?? '',
          application_url: job.applicationUrl,
        }
      : null;
  });

  protected validRequest(): boolean {
    return (
      validAiOptions(this.aiOptions()) &&
      this.question.trim().length > 0 &&
      this.question.length <= 10000 &&
      this.context.length <= 20000 &&
      this.maxWords !== null &&
      Number.isInteger(this.maxWords) &&
      this.maxWords >= 1 &&
      this.maxWords <= 1000
    );
  }

  protected generate(): void {
    const maxWords = this.maxWords;
    if (this.busy() || !this.validRequest() || maxWords === null) {
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.copyMessage.set('');
    this.service
      .answer({
        question: this.question.trim(),
        additional_context: this.context.trim() || null,
        max_words: maxWords,
        job: this.targetJob(),
        ai_options: this.aiOptions(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (answer): void => {
          this.response.set(answer);
          this.draft = answer.answer ?? '';
          this.answerLimit.set(maxWords);
          this.busy.set(false);
        },
        error: (error: unknown): void => {
          this.busy.set(false);
          this.error.set(
            apiError(error, 'Could not draft an answer. Your inputs are preserved; try again.'),
          );
        },
      });
  }

  protected wordCount(): number {
    return this.draft.trim() ? this.draft.trim().split(/\s+/).length : 0;
  }

  protected copyAnswer(): void {
    if (!this.draft.trim()) {
      return;
    }
    this.copyMessage.set(
      this.clipboard.copy(this.draft.trim())
        ? 'Copied. Ready for your application.'
        : 'Select the answer and copy it manually.',
    );
  }
}
