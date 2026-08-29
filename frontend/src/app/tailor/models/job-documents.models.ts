import type { DocumentSummary } from '../../jobs/models/user-data.models';

export interface DocumentVersion {
  readonly summary: DocumentSummary;
  readonly number: number | null;
  readonly latest: boolean;
}
