import * as validation from '../../shared/api-validation';

export interface ScrapeFailure {
  readonly stage: string;
  readonly error_type: string;
  readonly reason: string;
  readonly url: string | null;
}
export interface FailureDetails {
  readonly failures: readonly ScrapeFailure[];
  readonly failureCount: number;
  readonly failuresOmitted: number;
}
export function parseFailures(value: unknown): FailureDetails {
  if (value === undefined || value === null) {
    return { failures: [], failureCount: 0, failuresOmitted: 0 };
  }
  const row = validation.object(value);
  const failures = validation.list(row['failures'] ?? [], (value: unknown): ScrapeFailure => {
    const failure = validation.object(value);
    const url = validation.optionalText(failure['url']);
    if (url !== null) {
      const parsed = new URL(url);
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
        throw new Error('Invalid failure URL.');
      }
    }
    return {
      stage: validation.text(failure['stage']),
      error_type: validation.text(failure['error_type']),
      reason: validation.text(failure['reason']),
      url,
    };
  });
  return {
    failures,
    failureCount: Math.max(
      validation.number(row['failure_count'] ?? 0),
      validation.number(row['page_failures'] ?? 0) + validation.number(row['ai_failures'] ?? 0),
      failures.length,
    ),
    failuresOmitted: validation.number(row['failures_omitted'] ?? 0),
  };
}
