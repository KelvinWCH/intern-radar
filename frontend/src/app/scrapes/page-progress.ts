import type { ScrapePageProgress, ScrapePageState } from './models/page-progress.models';
import type { ScrapeTask } from './models/scrape.models';

function pageState(message: string, level: string): ScrapePageState | null {
  if (/^(Download|Extraction) failed for /.test(message) && level === 'error') {
    return 'failed';
  }
  if (message.startsWith('Saved for manual review: ')) {
    return 'review';
  }
  if (message.startsWith('Skipping https://') || message.startsWith('Skipping http://')) {
    return 'skipped';
  }
  if (/^Extracted \d+ jobs? from /.test(message)) {
    return 'completed';
  }
  if (message.startsWith('No matching job on ')) {
    return 'unmatched';
  }
  if (message.startsWith('Downloading ')) {
    return 'downloading';
  }
  if (message.startsWith('Using saved copy of ')) {
    return 'cached';
  }
  if (
    message.startsWith('Reusing saved extraction for ') ||
    message.startsWith('Sending ') ||
    message.startsWith('Reading basic facts from ')
  ) {
    return 'reading';
  }
  return null;
}

export function scrapePageProgress(task: ScrapeTask | null): readonly ScrapePageProgress[] {
  if (!task) {
    return [];
  }
  const pages = new Map<string, ScrapePageProgress>();
  const runs = new Map(task.runs.map((run) => [run.id, run.status]));
  const taskActive = task.status === 'queued' || task.status === 'running';
  for (const event of task.events) {
    const state = pageState(event.message, event.level);
    const address = /https?:\/\/[^\s]+/.exec(event.message)?.[0]?.replace(/[;:]+$/, '');
    if (!state || !address) {
      continue;
    }
    let url: URL;
    try {
      url = new URL(address);
    } catch {
      continue;
    }
    const normalizedUrl = `${url.origin}${url.pathname}`;
    const key = `${event.run_id}:${normalizedUrl}`;
    const previous = pages.get(key);
    if (state === 'skipped' && previous?.state === 'failed') {
      continue;
    }
    pages.set(key, {
      key,
      runId: event.run_id,
      url: normalizedUrl,
      host: url.hostname.replace(/^www\./, ''),
      path: url.pathname === '/' ? 'Job page' : url.pathname,
      state,
      downloaded:
        (previous?.downloaded ?? false) ||
        state === 'cached' ||
        state === 'reading' ||
        state === 'completed' ||
        state === 'unmatched' ||
        event.message.startsWith('Extraction failed for '),
      updatedAt: event.created_at,
      message: event.message,
    });
  }
  return [...pages.values()]
    .map((page): ScrapePageProgress => {
      const runStatus = runs.get(page.runId);
      const runFinished =
        runStatus !== undefined && runStatus !== 'running' && runStatus !== 'queued';
      return isPageWorking(page.state) && (!taskActive || runFinished)
        ? { ...page, state: 'interrupted' }
        : page;
    })
    .sort(
      (left, right): number =>
        Number(isPageWorking(right.state)) - Number(isPageWorking(left.state)) ||
        right.updatedAt - left.updatedAt ||
        left.key.localeCompare(right.key),
    );
}

export function isPageWorking(state: ScrapePageState): boolean {
  return state === 'downloading' || state === 'reading' || state === 'cached';
}
