import { relativeTimeUnits } from './constants/relative-time.constants';

export function relativeTime(seconds: number, now: number, units = 2): string {
  const difference = Math.round(now - seconds);
  let remaining = Math.abs(difference);
  if (remaining < 5) {
    return 'just now';
  }
  const parts: string[] = [];
  for (const [unit, size] of relativeTimeUnits) {
    if (parts.length === units) {
      break;
    }
    const count = Math.floor(remaining / size);
    if (count > 0) {
      parts.push(`${String(count)} ${unit}${count === 1 ? '' : 's'}`);
      remaining -= count * size;
    } else if (parts.length) {
      break;
    }
  }
  return difference >= 0 ? `${parts.join(' ')} ago` : `in ${parts.join(' ')}`;
}
