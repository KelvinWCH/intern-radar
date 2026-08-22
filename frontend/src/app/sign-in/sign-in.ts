import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { apiError } from '../shared/api-error';
import { SignInSession } from './sign-in-session';

interface SessionResponse {
  readonly token: string;
  readonly expires_at: number;
}

export function returnPath(next: string | null): string {
  return next?.startsWith('/') && !next.startsWith('//') && !next.startsWith('/sign-in')
    ? next
    : '/';
}

@Component({
  selector: 'app-sign-in',
  imports: [FormsModule],
  templateUrl: './sign-in.html',
  styleUrl: './sign-in.scss',
})
export class SignIn {
  private readonly session = inject(SignInSession);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  protected password = '';
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  protected submit(): void {
    if (this.busy() || !this.password) {
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.http
      .post<SessionResponse>('/api/auth/session', { password: this.password })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ token, expires_at }): void => {
          this.session.save(token, expires_at);
          this.password = '';
          void this.router.navigateByUrl(returnPath(this.route.snapshot.queryParamMap.get('next')));
        },
        error: (error: unknown): void => {
          this.busy.set(false);
          this.error.set(apiError(error, 'Could not sign in. Try again.'));
        },
      });
  }
}
