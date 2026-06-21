export type ScrapeStepKind =
  | 'start'
  | 'fetch'
  | 'download'
  | 'cache'
  | 'browser'
  | 'ai'
  | 'extract'
  | 'skip'
  | 'save'
  | 'done'
  | 'error'
  | 'info';
