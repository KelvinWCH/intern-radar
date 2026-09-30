import * as validation from '../../shared/api-validation';
import type { PageNavigation } from '../../shared/models/pagination.models';
import { parseNavigation } from '../../shared/pagination';
import type { FailureDetails } from './failure.models';
import { parseFailures } from './failure.models';
import type { ScrapeTrigger } from './trigger.models';
import { parseScrapeTrigger } from './trigger.models';
export interface ScrapeSource {
  readonly id: string;
  readonly name: string;
  readonly group: string;
  readonly enabled: boolean;
  readonly source_name: string | null;
  readonly reason: string | null;
}
export interface ScrapeRequest {
  readonly request_id: string;
  readonly sources: readonly string[];
  readonly max_runtime_seconds: number;
  readonly use_ai?: boolean;
  readonly ai_model?: string | null;
  readonly max_ai_calls: number;
  readonly max_downloads: number;
  readonly max_age_days: number;
  readonly include_older_postings?: boolean;
}
export interface ScrapeMetric {
  readonly label: string;
  readonly value: number;
  readonly seconds: boolean;
}
export interface ScrapeRun extends FailureDetails {
  readonly id: string;
  readonly source: string;
  readonly trigger: ScrapeTrigger | null;
  readonly status: string;
  readonly started_at: number;
  readonly finished_at: number | null;
  readonly elapsed_seconds: number;
  readonly fetched: number;
  readonly matched: number;
  readonly created: number;
  readonly updated: number;
  readonly unchanged: number;
  readonly error: string | null;
  readonly phase: string | null;
  readonly items_done: number | null;
  readonly items_total: number | null;
  readonly input_tokens: number | null;
  readonly output_tokens: number | null;
  readonly performance: readonly ScrapeMetric[];
}
export interface ScrapeEvent {
  readonly id: string;
  readonly run_id: string;
  readonly created_at: number;
  readonly level: 'info' | 'warning' | 'error';
  readonly message: string;
}
export interface ScheduledScrapeControl {
  readonly id: string;
  readonly group: string;
  readonly started_at: number;
  readonly cancel_requested: boolean;
}
export interface ScrapeActivity {
  readonly busy: boolean;
  readonly runs: readonly ScrapeRun[];
  readonly events: readonly ScrapeEvent[];
  readonly scheduled?: ScheduledScrapeControl | null;
}
export interface ScrapeUsage {
  readonly input_tokens: number;
  readonly output_tokens: number;
}
export interface ScrapeProgress {
  readonly sources_total: number;
  readonly sources_finished: number;
  readonly current_source: string | null;
  readonly phase: string | null;
  readonly items_done: number | null;
  readonly items_total: number | null;
  readonly percent: number;
}
export interface ScrapeTask {
  readonly id: string;
  readonly settings: ScrapeRequest;
  readonly status: string;
  readonly created_at: number;
  readonly started_at: number | null;
  readonly finished_at: number | null;
  readonly elapsed_seconds: number;
  readonly cancel_requested: boolean;
  readonly error: string | null;
  readonly runs: readonly ScrapeRun[];
  readonly events: readonly ScrapeEvent[];
  readonly usage: ScrapeUsage;
  readonly progress: ScrapeProgress;
}
export interface ScrapeHistoryPage extends PageNavigation {
  readonly items: readonly ScrapeRun[];
}
export function parseScrapeSource(value: unknown): ScrapeSource {
  const row = validation.object(value);
  return {
    id: validation.text(row['id']),
    name: validation.text(row['name']),
    group: validation.text(row['group']),
    enabled: validation.boolean(row['enabled']),
    source_name: validation.optionalText(row['source_name']),
    reason: validation.optionalText(row['reason']),
  };
}
export function parseScrapeRun(value: unknown): ScrapeRun {
  const row = validation.object(value);
  const metrics: ScrapeMetric[] = [];
  if (row['performance'] !== null && row['performance'] !== undefined) {
    const performance = validation.object(row['performance']);
    for (const [key, label, seconds] of [
      ['elapsed_seconds', 'Total wall time', true],
      ['discovery_seconds', 'Discovery', true],
      ['download_seconds', 'Page downloads', true],
      ['ai_seconds', 'AI processing', true],
      ['persistence_seconds', 'Storage', true],
      ['downloads', 'Downloads', false],
      ['page_cache_hits', 'Page cache hits', false],
      ['page_failures', 'Page failures', false],
      ['browser_reads', 'Browser reads', false],
      ['browser_fallbacks', 'Browser fallbacks', false],
      ['ai_calls', 'AI calls', false],
      ['ai_cache_hits', 'AI cache hits', false],
      ['shared_cache_hits', 'Shared cache hits', false],
      ['ai_failures', 'AI failures', false],
      ['documents', 'Documents processed', false],
      ['jobs_per_minute', 'Jobs / minute', false],
    ] as const) {
      if (performance[key] !== undefined) {
        metrics.push({ label, value: validation.number(performance[key]), seconds });
      }
    }
  }
  return {
    ...parseFailures(row['performance']),
    id: validation.identifier(row['id']),
    source: validation.text(row['source']),
    trigger: parseScrapeTrigger(row['trigger']),
    status: validation.text(row['status']),
    started_at: validation.number(row['started_at']),
    finished_at: validation.timestamp(row['finished_at']),
    elapsed_seconds: validation.number(row['elapsed_seconds']),
    fetched: validation.number(row['fetched']),
    matched: validation.number(row['matched']),
    created: validation.number(row['created']),
    updated: validation.number(row['updated']),
    unchanged: validation.number(row['unchanged']),
    error: validation.optionalText(row['error']),
    phase: validation.optionalText(row['phase']),
    items_done: optionalCount(row['items_done']),
    items_total: optionalCount(row['items_total']),
    input_tokens: optionalCount(row['input_tokens']),
    output_tokens: optionalCount(row['output_tokens']),
    performance: metrics,
  };
}
function optionalCount(value: unknown): number | null {
  return value === null || value === undefined ? null : validation.number(value);
}
function parseProgress(value: unknown): ScrapeProgress {
  const row = validation.object(value);
  return {
    sources_total: validation.number(row['sources_total']),
    sources_finished: validation.number(row['sources_finished']),
    current_source: validation.optionalText(row['current_source']),
    phase: validation.optionalText(row['phase']),
    items_done: optionalCount(row['items_done']),
    items_total: optionalCount(row['items_total']),
    percent: Math.min(100, validation.number(row['percent'])),
  };
}
function parseEvent(value: unknown): ScrapeEvent {
  const row = validation.object(value);
  const level = validation.text(row['level']);
  return {
    id: validation.identifier(row['id']),
    run_id: validation.identifier(row['run_id']),
    created_at: validation.number(row['created_at']),
    level: level === 'warning' || level === 'error' ? level : 'info',
    message: validation.text(row['message']),
  };
}
function parseUsage(value: unknown): ScrapeUsage {
  const row = validation.object(value);
  return {
    input_tokens: validation.number(row['input_tokens']),
    output_tokens: validation.number(row['output_tokens']),
  };
}
export function parseScrapeTask(value: unknown): ScrapeTask {
  const row = validation.object(value);
  const settings = validation.object(row['settings']);
  return {
    id: validation.text(row['id']),
    status: validation.text(row['status']),
    created_at: validation.number(row['created_at']),
    started_at: validation.timestamp(row['started_at']),
    finished_at: validation.timestamp(row['finished_at']),
    elapsed_seconds: validation.number(row['elapsed_seconds']),
    cancel_requested: validation.boolean(row['cancel_requested']),
    error: validation.optionalText(row['error']),
    runs: validation.list(row['runs'], parseScrapeRun),
    events: validation.list(row['events'] ?? [], parseEvent),
    usage: parseUsage(row['usage']),
    progress: parseProgress(row['progress']),
    settings: {
      request_id: validation.text(settings['request_id']),
      sources: validation.list(settings['sources'], validation.text),
      max_runtime_seconds: validation.number(settings['max_runtime_seconds']),
      use_ai: validation.boolean(settings['use_ai'] ?? false),
      ai_model: validation.optionalText(settings['ai_model'] ?? null),
      max_ai_calls: validation.number(settings['max_ai_calls']),
      max_downloads: validation.number(settings['max_downloads']),
      max_age_days: validation.number(settings['max_age_days']),
      include_older_postings: validation.boolean(settings['include_older_postings'] ?? false),
    },
  };
}
export function parseScrapeActivity(value: unknown): ScrapeActivity {
  const row = validation.object(value);
  const scheduled = row['scheduled'] == null ? null : validation.object(row['scheduled']);
  return {
    busy: validation.boolean(row['busy']),
    runs: validation.list(row['runs'], parseScrapeRun),
    events: validation.list(row['events'], parseEvent),
    scheduled: scheduled
      ? {
          id: validation.identifier(scheduled['id']),
          group: validation.text(scheduled['group']),
          started_at: validation.number(scheduled['started_at']),
          cancel_requested: validation.boolean(scheduled['cancel_requested']),
        }
      : null,
  };
}
export function parseScrapeHistory(value: unknown): ScrapeHistoryPage {
  const row = validation.object(value);
  const items = validation.list(row['items'], parseScrapeRun);
  return {
    items,
    ...parseNavigation(row, items.length),
  };
}
export function duration(seconds: number): string {
  const total = Math.floor(seconds);
  if (total < 60) {
    return `${String(total)}s`;
  }
  if (total < 3600) {
    return `${String(Math.floor(total / 60))}m ${String(total % 60)}s`;
  }
  return `${String(Math.floor(total / 3600))}h ${String(Math.floor((total % 3600) / 60))}m`;
}
