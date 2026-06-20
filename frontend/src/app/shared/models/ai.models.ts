import * as validation from '../api-validation';

export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export const reasoningEfforts: readonly {
  readonly value: ReasoningEffort;
  readonly label: string;
}[] = [
  { value: 'none', label: 'None' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'xhigh', label: 'Extra high' },
  { value: 'max', label: 'Max' },
];

export interface AiModelOptions {
  readonly model?: string | null;
  readonly temperature?: number | null;
  readonly max_output_tokens?: number | null;
  readonly reasoning_effort?: ReasoningEffort | null;
}

export type AiNumberField = Exclude<keyof AiModelOptions, 'model' | 'reasoning_effort'>;

export type AiOptionsEdit =
  | { readonly field: 'model'; readonly value: string | null }
  | { readonly field: 'reasoning_effort'; readonly value: ReasoningEffort | null }
  | { readonly field: AiNumberField; readonly value: number | null };

export interface ModelChoices {
  readonly models: readonly string[];
  readonly warning: string | null;
}

export interface AiUsage {
  readonly model_name: string;
  readonly calls: number;
  readonly input_tokens: number | null;
  readonly output_tokens: number | null;
}

function integer(value: unknown): number {
  const result = validation.number(value);
  if (!Number.isSafeInteger(result)) {
    throw new Error('Invalid AI token count.');
  }
  return result;
}

export function parseAiUsage(value: unknown): AiUsage | null {
  if (value === undefined || value === null) {
    return null;
  }
  const row = validation.object(value);
  const model = validation.text(row['model_name']);
  if (!model.trim()) {
    throw new Error('Invalid AI model name.');
  }
  return {
    model_name: model,
    calls: integer(row['calls']),
    input_tokens: row['input_tokens'] === null ? null : integer(row['input_tokens']),
    output_tokens: row['output_tokens'] === null ? null : integer(row['output_tokens']),
  };
}

export function validAiOptions(options: AiModelOptions): boolean {
  const bounded = (value: number | null | undefined, max: number): boolean =>
    value == null || (Number.isFinite(value) && value >= 0 && value <= max);
  return (
    (options.model == null ||
      (options.model.trim().length > 0 && options.model.trim().length <= 200)) &&
    bounded(options.temperature, 2) &&
    (options.max_output_tokens == null ||
      (Number.isSafeInteger(options.max_output_tokens) &&
        options.max_output_tokens >= 1 &&
        options.max_output_tokens <= 1_000_000)) &&
    (options.reasoning_effort == null ||
      reasoningEfforts.some((option): boolean => option.value === options.reasoning_effort))
  );
}

export function parseReasoningEffort(value: unknown): ReasoningEffort | null {
  if (value == null) {
    return null;
  }
  const effort = reasoningEfforts.find((option): boolean => option.value === value);
  if (!effort) {
    throw new Error('Invalid AI reasoning effort.');
  }
  return effort.value;
}

export function parseAiOptions(value: unknown): AiModelOptions {
  const row = validation.object(value);
  const options: AiModelOptions = {
    model: validation.optionalText(row['model']),
    temperature: validation.timestamp(row['temperature']),
    max_output_tokens: row['max_output_tokens'] === null ? null : integer(row['max_output_tokens']),
    reasoning_effort: parseReasoningEffort(row['reasoning_effort']),
  };
  if (!validAiOptions(options)) {
    throw new Error('Invalid AI model settings.');
  }
  return options;
}
