import * as validation from '../../shared/api-validation';
export interface TranscriptInfo {
  readonly filename: string;
  readonly size: number;
  readonly page_count: number;
  readonly uploaded_at: number;
}
export function parseTranscriptInfo(value: unknown): TranscriptInfo | null {
  if (value === null) {
    return null;
  }
  const item = validation.object(value);
  return {
    filename: validation.text(item['filename']),
    size: validation.number(item['size']),
    page_count: validation.number(item['page_count']),
    uploaded_at: validation.number(item['uploaded_at']),
  };
}
