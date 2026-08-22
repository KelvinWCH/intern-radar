import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import type { Observable } from 'rxjs';
import { map, tap, timeout } from 'rxjs';
import type { DocumentDownload } from '../tailor/models/document.models';
import { downloadFilename } from '../tailor/models/document.models';
import type { TranscriptInfo } from './models/transcript.models';
import { parseTranscriptInfo } from './models/transcript.models';

export const transcriptMaxBytes = 5 * 1024 * 1024;

@Injectable({ providedIn: 'root' })
export class TranscriptService {
  private readonly http = inject(HttpClient);
  private readonly current = signal<TranscriptInfo | null | undefined>(undefined);
  readonly transcript = this.current.asReadonly();

  load(): Observable<TranscriptInfo | null> {
    return this.http.get<unknown>('/api/resumes/transcript').pipe(
      timeout(30000),
      map(parseTranscriptInfo),
      tap((info): void => {
        this.current.set(info);
      }),
    );
  }

  upload(file: File): Observable<TranscriptInfo | null> {
    const body = new FormData();
    body.append('file', file);
    return this.http.put<unknown>('/api/resumes/transcript', body).pipe(
      map(parseTranscriptInfo),
      tap((info): void => {
        this.current.set(info);
      }),
    );
  }

  remove(): Observable<unknown> {
    return this.http.delete('/api/resumes/transcript').pipe(
      tap((): void => {
        this.current.set(null);
      }),
    );
  }

  download(): Observable<DocumentDownload> {
    return this.http
      .get('/api/resumes/transcript/pdf', { responseType: 'blob', observe: 'response' })
      .pipe(
        map((response): DocumentDownload => {
          const blob = response.body;
          if (!blob || blob.size === 0 || blob.type !== 'application/pdf') {
            throw new Error('Invalid download.');
          }
          return {
            blob,
            filename:
              downloadFilename(response.headers.get('Content-Disposition'), 'pdf') ??
              'Transcript.pdf',
          };
        }),
      );
  }
}
