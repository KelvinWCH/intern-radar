import { parseNavigation } from './pagination';

describe('Pagination bounds', (): void => {
  it.each([
    { limit: 101, offset: 0, total: 200 },
    { limit: 20, offset: -1, total: 20 },
    { limit: 20.5, offset: 0, total: 20 },
  ])('rejects unsafe page metadata', (row): void => {
    expect(() => parseNavigation(row, 0)).toThrow();
  });
});
