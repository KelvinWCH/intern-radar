import { HttpErrorResponse } from '@angular/common/http';

interface Issue {
  readonly path: readonly (string | number)[];
  readonly message: string;
  readonly unknownField: boolean;
}

const REQUEST_PARTS = new Set(['body', 'query', 'path']);
const MAX_GROUPS = 4;

export function apiError(error: unknown, fallback: string): string {
  if (!(error instanceof HttpErrorResponse)) {
    return fallback;
  }
  if (error.status === 0) {
    return 'Could not reach the backend. Your inputs are preserved; try again.';
  }
  const body: unknown = error.error;
  if (
    typeof body === 'object' &&
    body !== null &&
    'detail' in body &&
    typeof body.detail === 'string'
  ) {
    return body.detail;
  }
  if (typeof body === 'object' && body !== null && 'detail' in body && Array.isArray(body.detail)) {
    const issues = (body.detail as readonly unknown[]).flatMap(issue);
    if (issues.length) {
      return describe(issues);
    }
  }
  if ([502, 503, 504].includes(error.status)) {
    return `${fallback} The backend is unavailable or restarting (HTTP ${String(error.status)}); try again shortly.`;
  }
  return error.status === 422
    ? 'Check required fields and input limits, then try again.'
    : fallback;
}

function issue(detail: unknown): Issue[] {
  if (
    typeof detail !== 'object' ||
    detail === null ||
    !('msg' in detail) ||
    typeof detail.msg !== 'string'
  ) {
    return [];
  }
  const location: readonly unknown[] =
    'loc' in detail && Array.isArray(detail.loc) ? detail.loc : [];
  return [
    {
      path: location.filter(
        (part): part is string | number =>
          (typeof part === 'string' && !REQUEST_PARTS.has(part)) || typeof part === 'number',
      ),
      message: detail.msg.replace(/^Value error, /u, ''),
      unknownField: 'type' in detail && detail.type === 'extra_forbidden',
    },
  ];
}

function describe(issues: readonly Issue[]): string {
  const groups = new Map<string, { issue: Issue; indices: number[] }>();
  for (const item of issues) {
    const position = item.path.findIndex((part): boolean => typeof part === 'number');
    const shape = item.path.map((part): string => (typeof part === 'number' ? '#' : part));
    const key = `${shape.join('\u0000')}\u0001${item.message}`;
    const group = groups.get(key) ?? { issue: item, indices: [] };
    const index = item.path[position];
    if (typeof index === 'number' && !group.indices.includes(index)) {
      group.indices.push(index);
    }
    groups.set(key, group);
  }
  const unknown: string[] = [];
  const invalid: string[] = [];
  for (const { issue: item, indices } of groups.values()) {
    const field = label(item.path, indices);
    if (item.unknownField) {
      unknown.push(field);
    } else {
      invalid.push(`${field ? `${field}: ` : ''}${item.message}`);
    }
  }
  if (!invalid.length) {
    return (
      'The server did not recognize some fields, so it is probably running an older version ' +
      'than this page. Nothing was saved and your edits are still here; reload after the ' +
      `backend update finishes, then try again. Unrecognized: ${limit(unknown)}.`
    );
  }
  return limit(
    unknown.length ? [...invalid, `Unrecognized fields: ${unknown.join(', ')}`] : invalid,
  );
}

function limit(lines: readonly string[]): string {
  const shown = lines.slice(0, MAX_GROUPS).join('; ');
  const hidden = lines.length - MAX_GROUPS;
  return hidden > 0 ? `${shown}; and ${String(hidden)} more` : shown;
}

function label(path: readonly (string | number)[], indices: readonly number[]): string {
  const parts: string[] = [];
  let first = true;
  for (const part of path) {
    if (typeof part === 'number') {
      const range = first && indices.length ? positions(indices) : `#${String(part + 1)}`;
      first = false;
      const owner = parts.pop();
      parts.push(owner === undefined ? range : `${owner} ${range}`);
    } else {
      const text = part.replaceAll('_', ' ');
      parts.push(text.charAt(0).toUpperCase() + text.slice(1));
    }
  }
  return parts.join(' › ');
}

function positions(indices: readonly number[]): string {
  const sorted = [...indices].sort((a, b): number => a - b);
  const ranges: string[] = [];
  let start = sorted[0] ?? 0;
  let previous = start;
  for (const index of [...sorted.slice(1), Number.NaN]) {
    if (index === previous + 1) {
      previous = index;
      continue;
    }
    ranges.push(
      start === previous
        ? `#${String(start + 1)}`
        : `#${String(start + 1)}–#${String(previous + 1)}`,
    );
    start = index;
    previous = index;
  }
  return ranges.join(', ');
}
