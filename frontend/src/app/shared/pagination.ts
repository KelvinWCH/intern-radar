import * as validation from './api-validation';
import type { PageNavigation } from './models/pagination.models';

export function parseNavigation(row: Record<string, unknown>, count: number): PageNavigation {
  const limit = validation.number(row['limit']);
  const offset = validation.number(row['offset']);
  const total = row['total'] === null ? null : validation.number(row['total']);
  const nextCursor = validation.optionalText(row['next_cursor'] ?? null);
  if (
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    count > limit ||
    !Number.isSafeInteger(offset) ||
    offset < 0 ||
    (total !== null &&
      (!Number.isSafeInteger(total) || total < 0 || (count > 0 && offset + count > total))) ||
    (nextCursor !== null && (nextCursor.length === 0 || nextCursor.length > 1024))
  ) {
    throw new Error('Invalid pagination response.');
  }
  return { total, limit, offset, nextCursor };
}

export class CursorNavigation {
  private readonly positions = new Map<number, string>([[0, '']]);

  reset(): void {
    this.positions.clear();
    this.positions.set(0, '');
  }

  cursor(offset: number): string | undefined {
    return this.positions.get(offset);
  }

  remember(page: PageNavigation): void {
    const next = page.offset + page.limit;
    if (page.nextCursor) {
      this.positions.set(next, page.nextCursor);
    } else {
      this.positions.delete(next);
    }
    if (this.positions.size > 100) {
      const oldest = [...this.positions.keys()].find((key): boolean => key !== 0);
      if (oldest !== undefined) {
        this.positions.delete(oldest);
      }
    }
  }
}
