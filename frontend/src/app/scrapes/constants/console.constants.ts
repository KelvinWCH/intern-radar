import type { ScrapeStepKind } from '../models/console.models';

export const scrapeStepLabels: Record<ScrapeStepKind, string> = {
  start: 'START',
  fetch: 'FETCH',
  download: 'PAGE',
  cache: 'CACHE',
  browser: 'CHROME',
  ai: 'AI',
  extract: 'FOUND',
  skip: 'SKIP',
  save: 'SAVE',
  done: 'DONE',
  error: 'ERROR',
  info: 'INFO',
};
