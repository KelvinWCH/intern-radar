import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { signInInterceptor, SignInSession } from './sign-in-session';

describe('SignInSession', (): void => {
  beforeEach((): void => {
    localStorage.removeItem('intern-radar.session');
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([signInInterceptor])),
        provideHttpClientTesting(),
      ],
    });
  });

  afterEach((): void => {
    TestBed.inject(HttpTestingController).verify();
    localStorage.removeItem('intern-radar.session');
  });

  it('adds the token to api requests', (): void => {
    const session = TestBed.inject(SignInSession);
    const client = TestBed.inject(HttpClient);
    const http = TestBed.inject(HttpTestingController);
    session.save('token-1', Date.now() / 1000 + 60);
    client.get('/api/jobs').subscribe();
    expect(http.expectOne('/api/jobs').request.headers.get('Authorization')).toBe('Bearer token-1');
    client.get('/favicon.ico').subscribe();
    expect(http.expectOne('/favicon.ico').request.headers.has('Authorization')).toBe(false);
    session.save('token-2', Date.now() / 1000 - 1);
    expect(session.token()).toBeNull();
  });

  it('goes to sign in on a 401', async (): Promise<void> => {
    const session = TestBed.inject(SignInSession);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    session.save('stale', Date.now() / 1000 + 60);
    let failed = false;
    TestBed.inject(HttpClient)
      .get('/api/jobs')
      .subscribe({ error: (): void => void (failed = true) });
    TestBed.inject(HttpTestingController)
      .expectOne('/api/jobs')
      .flush(
        { detail: 'Sign in to use this backend.', code: 'sign_in_required' },
        { status: 401, statusText: 'Unauthorized' },
      );
    await Promise.resolve();
    expect(failed).toBe(true);
    expect(session.token()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/sign-in'], { queryParams: { next: '/' } });
  });
});
