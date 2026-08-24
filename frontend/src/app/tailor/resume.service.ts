import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { catchError, map, of, throwError } from 'rxjs';
import type { GeneratedResume, ResumeProfile, TailoringJob } from './models/resume.models';
import { parseGeneratedResume, parseLatex, parseResumeProfile } from './models/resume.models';
import { AiDefaults } from '../settings/ai-defaults';

@Injectable({ providedIn: 'root' })
export class ResumeService {
  private readonly http = inject(HttpClient);
  private readonly preferences = inject(AiDefaults);

  profile(): Observable<ResumeProfile | null> {
    return this.http.get<unknown>('/api/resumes/profile').pipe(
      map(parseResumeProfile),
      catchError((error: unknown) =>
        error instanceof HttpErrorResponse && error.status === 404
          ? of(null)
          : throwError(() => error),
      ),
    );
  }

  sourcePdf(): Observable<Blob> {
    return this.http.get('/api/resumes/profile/pdf', { responseType: 'blob' }).pipe(
      map((pdf): Blob => {
        if (pdf.type !== 'application/pdf' || pdf.size === 0 || pdf.size > 2_500_000) {
          throw new Error('Invalid source PDF response.');
        }
        return pdf;
      }),
    );
  }

  upload(file: File): Observable<ResumeProfile> {
    const body = new FormData();
    body.append('file', file);
    const { model, reasoning_effort } = this.preferences.options('upload');
    if (model) {
      body.append('ai_model', model);
    }
    if (reasoning_effort) {
      body.append('ai_reasoning_effort', reasoning_effort);
    }
    return this.http.post<unknown>('/api/resumes/upload', body).pipe(map(parseResumeProfile));
  }

  generate(job: TailoringJob): Observable<GeneratedResume> {
    return this.http.post<unknown>('/api/resumes/generate', job).pipe(map(parseGeneratedResume));
  }

  latex(resume: GeneratedResume): Observable<string> {
    return this.http.post<unknown>('/api/resumes/latex', resume).pipe(map(parseLatex));
  }
}
