export interface PageNavigation {
  readonly total: number | null;
  readonly limit: number;
  readonly offset: number;
  readonly nextCursor?: string | null;
}
