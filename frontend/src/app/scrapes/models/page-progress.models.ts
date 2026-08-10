export type ScrapePageState =
  | 'downloading'
  | 'reading'
  | 'cached'
  | 'completed'
  | 'unmatched'
  | 'failed'
  | 'skipped'
  | 'review'
  | 'interrupted';

export interface ScrapePageProgress {
  readonly key: string;
  readonly runId: string;
  readonly url: string;
  readonly host: string;
  readonly path: string;
  readonly state: ScrapePageState;
  readonly downloaded: boolean;
  readonly updatedAt: number;
  readonly message: string;
}
