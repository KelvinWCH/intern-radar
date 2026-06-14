export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
export function object(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error('Invalid API object.');
  }
  return value;
}
export function text(value: unknown): string {
  if (typeof value !== 'string') {
    throw new Error('Invalid API text.');
  }
  return value;
}
export function identifier(value: unknown): string {
  const result = text(value);
  if (!result.trim()) {
    throw new Error('Invalid API identifier.');
  }
  return result;
}
export function optionalText(value: unknown): string | null {
  return value === null ? null : text(value);
}
export function number(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error('Invalid API number.');
  }
  return value;
}
export function timestamp(value: unknown): number | null {
  return value === null ? null : number(value);
}
export function boolean(value: unknown): boolean {
  if (typeof value !== 'boolean') {
    throw new Error('Invalid API boolean.');
  }
  return value;
}
export function list<T>(value: unknown, parse: (value: unknown) => T): T[] {
  if (!Array.isArray(value)) {
    throw new Error('Invalid API list.');
  }
  return value.map((item: unknown): T => parse(item));
}
