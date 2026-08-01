import type { JobInput } from '../../jobs/models/job.models';
import type { AiModelOptions } from '../../shared/models/ai.models';
import * as validation from '../../shared/api-validation';

export interface QuestionRequest {
  readonly question: string;
  readonly job: JobInput | null;
  readonly additional_context: string | null;
  readonly max_words: number;
  readonly ai_options?: AiModelOptions;
}

export interface QuestionAnswer {
  readonly question: string;
  readonly answer: string | null;
  readonly missing_information: readonly string[];
  readonly word_count: number;
}

function nonblankText(value: unknown): string {
  const text = validation.text(value);
  if (!text.trim()) {
    throw new Error('The answer contains empty text.');
  }
  return text;
}

export function parseQuestionAnswer(value: unknown): QuestionAnswer {
  const response = validation.object(value);
  const question = nonblankText(response['question']);
  const answer = response['answer'] === null ? null : nonblankText(response['answer']);
  const missingInformation = validation.list(response['missing_information'], nonblankText);
  const wordCount = validation.number(response['word_count']);
  if (
    !Number.isSafeInteger(wordCount) ||
    wordCount > 1000 ||
    (answer === null
      ? wordCount !== 0 || missingInformation.length === 0
      : missingInformation.length > 0 || answer.trim().split(/\s+/).length !== wordCount)
  ) {
    throw new Error('The answer has inconsistent content.');
  }
  return { question, answer, missing_information: missingInformation, word_count: wordCount };
}
