import type { JobInput } from '../../jobs/models/job.models';
import type { AiModelOptions } from '../../shared/models/ai.models';
import * as validation from '../../shared/api-validation';

export interface CompletionContext {
  readonly purpose: 'question' | 'context' | 'guidance';
  readonly question?: string;
  readonly additional_context?: string;
  readonly job?: JobInput | null;
  readonly document_id?: string | null;
  readonly review_issue?: string;
  readonly ai_options?: AiModelOptions;
}

export interface ContextCompletion {
  readonly continuation: string | null;
  readonly model: string;
}

export function parseContextCompletion(value: unknown): ContextCompletion {
  const row = validation.object(value);
  const continuation = row['continuation'] === null ? null : validation.text(row['continuation']);
  const model = validation.text(row['model']);
  if (
    !model.trim() ||
    (continuation !== null &&
      (!continuation.trim() || continuation.length > 500 || /[\r\n]/.test(continuation)))
  ) {
    throw new Error('Invalid sentence suggestion.');
  }
  return { continuation, model };
}
