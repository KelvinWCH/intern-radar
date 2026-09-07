import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import type { Observable } from 'rxjs';
import { of } from 'rxjs';
import { App } from './app';
import { routes } from './app.routes';
import { JobsService } from './jobs/jobs.service';
import type { JobPage } from './jobs/models/job.models';
import type { ScrapeSummary } from './scrapes/models/scrape-summary.models';
import type { ResumeProfile } from './tailor/models/resume.models';
import { ResumeService } from './tailor/resume.service';

const emptySummary: ScrapeSummary = {
  created: 0,
  duplicates: 0,
  updated: 0,
  runs: 0,
  failedRuns: 0,
  runningRuns: 0,
  inputTokens: 0,
  outputTokens: 0,
  scrapeSeconds: 0,
};

describe('App', (): void => {
  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes),
        {
          provide: JobsService,
          useValue: {
            forDay: (): Observable<JobPage> => of({ items: [], total: 0, limit: 100, offset: 0 }),
            scrapeSummaryForDay: (): Observable<ScrapeSummary> => of(emptySummary),
          },
        },
        {
          provide: ResumeService,
          useValue: { profile: (): Observable<ResumeProfile | null> => of(null) },
        },
      ],
    }).compileComponents();
  });

  it('moves between pages', async (): Promise<void> => {
    const fixture = TestBed.createComponent(App);
    const element = fixture.nativeElement as HTMLElement;
    await TestBed.inject(Router).navigateByUrl('/');
    await fixture.whenStable();
    expect(element.querySelector('h1')?.textContent).toBe('Intern Radar');
    expect(element.querySelector('app-daily-report')).not.toBeNull();
    await TestBed.inject(Router).navigateByUrl('/jobs/new');
    await fixture.whenStable();
    expect(element.textContent).toContain('Save job');
    element.querySelector<HTMLAnchorElement>('a[href="/tailor"]')?.click();
    await fixture.whenStable();
    expect(element.querySelector('app-tailor')).not.toBeNull();
    expect(element.textContent).toContain('Tailor your application');
    element.querySelector<HTMLAnchorElement>('.brand')?.click();
    await fixture.whenStable();
    expect(element.querySelector('app-daily-report')).not.toBeNull();
  });
});
