export type ScrapeTrigger = 'manual' | 'cron' | 'cli';

export function parseScrapeTrigger(value: unknown): ScrapeTrigger | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (value === 'manual' || value === 'cron' || value === 'cli') {
    return value;
  }
  throw new Error('Invalid scrape trigger.');
}

export function scrapeTriggerLabel(trigger: ScrapeTrigger | null): string {
  switch (trigger) {
    case 'manual':
      return 'Manual';
    case 'cron':
      return 'Cron / scheduled';
    case 'cli':
      return 'CLI';
    case null:
      return 'Not recorded';
  }
}
