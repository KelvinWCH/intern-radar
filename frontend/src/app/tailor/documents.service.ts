import { DOCUMENT } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { EMPTY, expand, map, of, retry, switchMap, throwError } from 'rxjs';
import { visibleDelay } from '../shared/visible-poll';
import { list } from '../shared/api-validation';
import type {
  DocumentDetail,
  DocumentDownload,
  DocumentTechnicalDetails,
  DocumentPage,
  TailoringProcess,
  TailorRequest,
} from './models/document.models';
import {
  downloadFilename,
  parseDocument,
  parseDocumentPage,
  parseTailoringProcess,
} from './models/document.models';
import { parseDocumentTechnicalDetails } from './models/document.models';
import type { ResearchReviewRequest } from './models/research.models';
import type { ReviewDecision } from './models/application-review.models';
import type { DraftPreview } from './models/resume-editor.models';
import { parseDraftPreview } from './models/resume-editor.models';
import type { GeneratedResume } from './models/resume.models';
import { resumePayload } from './models/resume.models';
import { AiDefaults } from '../settings/ai-defaults';

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly http = inject(HttpClient);
  private readonly document = inject(DOCUMENT);
  private readonly preferences = inject(AiDefaults);

  technical(id: string): Observable<DocumentTechnicalDetails> {
    return this.http.get<unknown>(`/api/documents/${encodeURIComponent(id)}/technical`).pipe(
      map(parseDocumentTechnicalDetails),
      map((result): DocumentTechnicalDetails => {
        if (result.id !== id) {
          throw new Error('Unexpected document technical details.');
        }
        return result;
      }),
    );
  }
  active(): Observable<readonly TailoringProcess[]> {
    return this.http
      .get<unknown>('/api/documents/active')
      .pipe(map((value): TailoringProcess[] => list(value, parseTailoringProcess)));
  }
  reviewApplication(id: string, decision: ReviewDecision): Observable<DocumentDetail> {
    return this.http
      .post<unknown>(`/api/documents/${encodeURIComponent(id)}/application-review`, decision)
      .pipe(map(parseDocument));
  }
  saveResume(id: string, revision: number, resume: GeneratedResume): Observable<DocumentDetail> {
    return this.http
      .put<unknown>(`/api/documents/${encodeURIComponent(id)}/resume`, {
        revision,
        resume: resumePayload(resume),
      })
      .pipe(map(parseDocument));
  }
  previewResume(resume: GeneratedResume): Observable<DraftPreview> {
    return this.http
      .post<unknown>('/api/resumes/draft-preview', resumePayload(resume))
      .pipe(map(parseDraftPreview));
  }
  control(id: string, action: 'pause' | 'resume' | 'cancel'): Observable<DocumentDetail> {
    return this.http
      .post<unknown>(`/api/documents/${encodeURIComponent(id)}/${action}`, null)
      .pipe(map(parseDocument));
  }
  reviewResearch(id: string, review: ResearchReviewRequest): Observable<DocumentDetail> {
    return this.http
      .post<unknown>(`/api/documents/${encodeURIComponent(id)}/research-review`, review)
      .pipe(map(parseDocument));
  }
  tailor(jobId: string, request: TailorRequest): Observable<DocumentDetail> {
    return this.start(jobId, request).pipe(
      switchMap((document) => this.watch(document.id, document)),
    );
  }
  start(jobId: string, request: TailorRequest): Observable<DocumentDetail> {
    const resume = this.preferences.resolve(
      'resume',
      request.resume_ai_options ?? request.ai_options,
    );
    const resolved: TailorRequest = {
      ...request,
      ...(request.include_resume ? { ai_options: resume, resume_ai_options: resume } : {}),
      research_ai_options: this.preferences.resolve('research', request.research_ai_options),
      ...(request.include_cover_letter
        ? {
            cover_letter_ai_options: this.preferences.resolve(
              'letter',
              request.cover_letter_ai_options,
            ),
          }
        : {}),
      reviewer_ai_options: this.preferences.resolve('review', request.reviewer_ai_options),
    };
    return this.http
      .post<unknown>(`/api/jobs/${encodeURIComponent(jobId)}/tailor-tasks`, resolved)
      .pipe(map(parseDocument));
  }
  watch(id: string, initial?: DocumentDetail): Observable<DocumentDetail> {
    const read = this.get(id).pipe(
      retry({
        count: 2,
        delay: (error: unknown, count: number) =>
          error instanceof HttpErrorResponse && (error.status === 0 || error.status >= 500)
            ? visibleDelay(this.document, count * 1500)
            : throwError((): unknown => error),
      }),
    );
    return (initial ? of(initial) : read).pipe(
      expand((document) =>
        document.status === 'running'
          ? visibleDelay(this.document, 1000).pipe(switchMap(() => read))
          : EMPTY,
      ),
    );
  }
  history(offset = 0, cursor = ''): Observable<DocumentPage> {
    return this.http.get<unknown>('/api/documents', { params: { limit: 20, offset, cursor } }).pipe(
      map((value): DocumentPage => {
        const page = parseDocumentPage(value);
        if (page.offset !== offset || page.limit !== 20 || (cursor && page.nextCursor === cursor)) {
          throw new Error('Unexpected document history page.');
        }
        return page;
      }),
    );
  }
  get(id: string): Observable<DocumentDetail> {
    return this.http
      .get<unknown>(`/api/documents/${encodeURIComponent(id)}`)
      .pipe(map(parseDocument));
  }
  download(
    id: string,
    kind: 'resume' | 'cover-letter',
    format: 'pdf' | 'tex',
    draft = false,
  ): Observable<DocumentDownload> {
    const path = `${draft ? 'unfitted/' : ''}${kind}/${format}`;
    return this.http
      .get(`/api/documents/${encodeURIComponent(id)}/${path}`, {
        responseType: 'blob',
        observe: 'response',
      })
      .pipe(
        map((response): DocumentDownload => {
          const blob = response.body;
          if (
            !blob ||
            blob.size === 0 ||
            blob.size > 2_500_000 ||
            (format === 'pdf' && blob.type !== 'application/pdf')
          ) {
            throw new Error('Invalid download.');
          }
          return {
            blob,
            filename:
              downloadFilename(response.headers.get('Content-Disposition'), format) ??
              `${kind}.${format}`,
          };
        }),
      );
  }

  downloadPackage(
    id: string,
    format: 'pdf' | 'zip',
    transcript: boolean,
  ): Observable<DocumentDownload> {
    return this.http
      .get(`/api/documents/${encodeURIComponent(id)}/package`, {
        params: { format, transcript },
        responseType: 'blob',
        observe: 'response',
      })
      .pipe(
        map((response): DocumentDownload => {
          const blob = response.body;
          const type = format === 'pdf' ? 'application/pdf' : 'application/zip';
          if (!blob || blob.size === 0 || blob.size > 20_000_000 || blob.type !== type) {
            throw new Error('Invalid download.');
          }
          return {
            blob,
            filename:
              downloadFilename(response.headers.get('Content-Disposition'), format) ??
              `application.${format}`,
          };
        }),
      );
  }
}
