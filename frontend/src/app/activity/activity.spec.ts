import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Activity } from './activity';
import type { ActivitySummary } from './models/activity.models';

const summary: ActivitySummary = {
  start_date: '2026-09-18',
  end_date: '2026-10-17',
  generated_at: 1792252800,
  total_applications: 12,
  active_days: 1,
  days: Array.from({ length: 30 }, (_, index) => ({
    date: new Date(Date.UTC(2026, 8, 18 + index)).toISOString().slice(0, 10),
    actions: index === 29 ? 3 : 0,
    applications: index === 29 ? 1 : 0,
    documents: index === 29 ? 1 : 0,
    resume_updates: index === 29 ? 1 : 0,
  })),
  pipeline: [
    { status: 'saved', count: 3 },
    { status: 'applied', count: 8 },
    { status: 'interviewing', count: 2 },
    { status: 'offered', count: 1 },
  ],
  recent: [
    {
      id: 'application:7',
      kind: 'application_marked',
      occurred_at: 1792252800,
      data: {
        job_id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
        company: 'Example',
        title: 'Intern',
        status: 'applied',
        document_id: null,
        profile_revision: null,
        backfilled: false,
      },
    },
  ],
};

describe('Activity', (): void => {
  let fixture: ComponentFixture<Activity>;
  let element: HTMLElement;
  let http: HttpTestingController;

  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [Activity],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Activity);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });
  afterEach((): void => {
    fixture.destroy();
    http.verify();
  });

  it('shows the activity page', async (): Promise<void> => {
    http.expectOne('/api/activity/summary?days=30').flush(summary);
    await fixture.whenStable();
    expect(element.querySelectorAll('.day-bar')).toHaveLength(30);
    expect(element.querySelectorAll('.pipeline-stage')).toHaveLength(4);
    expect(
      element.querySelector('a[href="/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3"]')
        ?.textContent,
    ).toContain('Intern');
    expect(element.querySelector('.day-detail')?.textContent).toContain('3 actions');
    element.querySelector<HTMLButtonElement>('.day-bar')?.click();
    await fixture.whenStable();
    expect(element.querySelector('.day-detail')?.textContent).toContain('0 actions');
  });
});
