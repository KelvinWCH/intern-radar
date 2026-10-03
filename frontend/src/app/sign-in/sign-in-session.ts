import { DOCUMENT } from '@angular/common';
import type { HttpInterceptorFn } from '@angular/common/http';
import { HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { isRecord } from '../shared/api-validation';

const storageKey = 'intern-radar.session';

interface SavedSession {
  readonly token: string;
  readonly expiresAt: number;
}

@Injectable({ providedIn: 'root' })
export class SignInSession {
  private readonly browser = inject(DOCUMENT).defaultView;

  token(): string | null {
    try {
      const saved: unknown = JSON.parse(this.browser?.localStorage.getItem(storageKey) ?? 'null');
      if (!isRecord(saved)) {
        return null;
      }
      const token = saved['token'];
      const expiresAt = saved['expiresAt'];
      if (typeof token !== 'string' || typeof expiresAt !== 'number') {
        return null;
      }
      return expiresAt * 1000 > Date.now() ? token : null;
    } catch {
      return null;
    }
  }

  save(token: string, expiresAt: number): void {
    const session: SavedSession = { token, expiresAt };
    this.browser?.localStorage.setItem(storageKey, JSON.stringify(session));
  }

  clear(): void {
    this.browser?.localStorage.removeItem(storageKey);
  }
}

export function signInRequired(error: unknown): boolean {
  if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
    return false;
  }
  const body: unknown = error.error;
  return typeof body === 'object' && body !== null && 'code' in body
    ? body.code === 'sign_in_required'
    : false;
}

export const signInInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith('/api/')) {
    return next(request);
  }
  const session = inject(SignInSession);
  const router = inject(Router);
  const token = session.token();
  const sent = token
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request;
  return next(sent).pipe(
    catchError((error: unknown) => {
      if (signInRequired(error)) {
        session.clear();
        if (!router.url.startsWith('/sign-in')) {
          void router.navigate(['/sign-in'], { queryParams: { next: router.url } });
        }
      }
      return throwError(() => error);
    }),
  );
};
