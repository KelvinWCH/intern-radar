import * as validation from '../../shared/api-validation';
export interface JobQuery {
  scope?: 'eligible' | 'all';
  flagged?: boolean;
  deleted?: boolean;
  q: string;
  company: string;
  location: string;
  source: string;
  application_status: string;
  activity: string;
  tracked: boolean;
  sort:
    'recent' | 'posted' | 'prestige' | 'engineering' | 'match' | 'company' | 'title' | 'location';
  match?: '' | '60' | '75' | '85';
  toronto?: boolean;
  from: string;
  before: string;
}
export interface JobOverview {
  readonly total: number;
  readonly statuses: Readonly<Record<string, number>>;
  readonly sources: readonly string[];
}
export function parseOverview(value: unknown): JobOverview {
  const row = validation.object(value);
  const statuses = validation.object(row['statuses']);
  return {
    total: validation.number(row['total']),
    sources: validation.list(row['sources'], validation.text),
    statuses: Object.fromEntries(
      Object.entries(statuses).map(([key, count]): [string, number] => [
        key,
        validation.number(count),
      ]),
    ),
  };
}
