import type { DocumentSummary } from '../../jobs/models/user-data.models';

export const documentStatusLabels: Readonly<Record<DocumentSummary['status'], string>> = {
  running: 'In progress',
  awaiting_review: 'Needs review',
  completed: 'Saved',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export const versionClockIntervalMs = 30_000;
