import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ParamMap } from '@angular/router';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { returnPath, SignIn } from './sign-in';
import { SignInSession } from './sign-in-session';

describe('Sign-in page', (): void => {
  const next = { value: '/jobs/42?tab=notes' as string | null };

  beforeEach((): void => {
    localStorage.removeItem('intern-radar.session');
    TestBed.configureTestingModule({
      imports: [SignIn],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              get queryParamMap(): ParamMap {
                return convertToParamMap(next.value === null ? {} : { next: next.value });
              },
            },
          },
        },
      ],
    });
  });

  afterEach((): void => {
    TestBed.inject(HttpTestingController).verify();
    localStorage.removeItem('intern-radar.session');
  });

  async function signIn(password: string): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(SignIn);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    const input = page.querySelector<HTMLInputElement>('input[type="password"]');
    if (!input) {
      throw new Error('The page has no password field.');
    }
    input.value = password;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    page.querySelector('form')?.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    return page;
  }

  it('saves the session and goes back', async (): Promise<void> => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await signIn('correct horse battery');
    const request = TestBed.inject(HttpTestingController).expectOne('/api/auth/session');
    expect(request.request.body).toEqual({ password: 'correct horse battery' });
    request.flush({ token: 'signed-token', expires_at: Date.now() / 1000 + 3600 });
    expect(TestBed.inject(SignInSession).token()).toBe('signed-token');
    expect(navigate).toHaveBeenCalledWith('/jobs/42?tab=notes');
  });

  it('only returns to paths inside this app', (): void => {
    expect(returnPath('/documents/7')).toBe('/documents/7');
    for (const unsafe of [null, '', 'https://evil.example', '//evil.example', '/sign-in?next=/']) {
      expect(returnPath(unsafe)).toBe('/');
    }
  });
});
