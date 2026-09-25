import type { DocumentSummary } from '../jobs/models/user-data.models';

export function pendingTailoringAttempt(
  documents: readonly DocumentSummary[],
): DocumentSummary | undefined {
  const running = documents.find((document) => document.status === 'running');
  if (running) {
    return running;
  }
  const newest = documents.reduce<DocumentSummary | undefined>(
    (latest, document) => (!latest || document.created_at > latest.created_at ? document : latest),
    undefined,
  );
  return newest?.status === 'awaiting_review' ? newest : undefined;
}
