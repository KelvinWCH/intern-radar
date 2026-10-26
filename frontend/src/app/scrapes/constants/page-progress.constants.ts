import type { ScrapePageState } from '../models/page-progress.models';

export const scrapePageLabels: Readonly<Record<ScrapePageState, string>> = {
  downloading: 'Downloading',
  reading: 'Extracting',
  cached: 'Reading saved copy',
  completed: 'Extracted',
  unmatched: 'No match',
  failed: 'Failed',
  skipped: 'Skipped',
  review: 'Needs review',
  interrupted: 'No final update',
};

export const scrapeFlowStages = [
  { label: 'Discover', icon: 'pi-compass', phase: 'discovering' },
  { label: 'Read pages', icon: 'pi-file', phase: 'reading and extracting' },
  { label: 'Save jobs', icon: 'pi-database', phase: 'saving' },
  { label: 'Done', icon: 'pi-check', phase: 'completed' },
] as const;
