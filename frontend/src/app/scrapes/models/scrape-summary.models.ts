export interface ScrapeSummary {
  readonly created: number;
  readonly duplicates: number;
  readonly updated: number;
  readonly runs: number;
  readonly failedRuns: number;
  readonly runningRuns: number;
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly scrapeSeconds: number;
}

export interface ScrapeSummaryState {
  readonly status: 'loading' | 'ready' | 'error';
  readonly summary: ScrapeSummary | null;
}

export function parseScrapeSummary(value: unknown): ScrapeSummary {
  if (typeof value !== 'object' || value === null) {
    throw new Error('Invalid scrape summary.');
  }
  return {
    created: counter(Reflect.get(value, 'created')),
    duplicates: counter(Reflect.get(value, 'duplicates')),
    updated: counter(Reflect.get(value, 'updated')),
    runs: counter(Reflect.get(value, 'runs')),
    failedRuns: counter(Reflect.get(value, 'failed_runs')),
    runningRuns: counter(Reflect.get(value, 'running_runs')),
    inputTokens: counter(Reflect.get(value, 'input_tokens')),
    outputTokens: counter(Reflect.get(value, 'output_tokens')),
    scrapeSeconds: counter(Reflect.get(value, 'scrape_seconds')),
  };
}

function counter(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new Error('Invalid scrape count.');
  }
  return value;
}
