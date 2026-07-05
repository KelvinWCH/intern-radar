import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { JobDetail } from './job-detail';

const apiJob = {
  id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
  source: 'Example feed',
  source_type: 'scraped',
  details_version: 3,
  company: 'Example',
  title: 'Engineering Intern',
  application_url: null,
  apply_url: null,
  source_job_id: 'REQ-7',
  raw_description: null,
  locations: ['Toronto'],
  terms: ['Summer 2027'],
  category: null,
  summary: null,
  active: true,
  date_posted: Date.UTC(2026, 9, 15) / 1000,
  date_updated: null,
  first_seen_at: Date.UTC(2026, 9, 16, 12) / 1000,
  last_seen_at: Date.UTC(2026, 9, 17, 12) / 1000,
  details_updated_at: null,
  user: {
    status: 'new',
    notes: '',
    applied_at: null,
    follow_up_at: null,
    updated_at: null,
    version: 0,
    documents: [],
  },
};

describe('JobDetail', (): void => {
  let fixture: ComponentFixture<JobDetail>;
  let http: HttpTestingController;
  let element: HTMLElement;
  let route: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let query: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  function button(label: string): HTMLButtonElement {
    const found = Array.from(element.querySelectorAll('button')).find((item): boolean =>
      item.textContent.includes(label),
    );
    if (!found) {
      throw new Error(`Missing button ${label}`);
    }
    return found;
  }
  function stat(label: string): string | undefined {
    return Array.from(element.querySelectorAll('app-job-stats dt'))
      .find((item): boolean => item.textContent.trim() === label)
      ?.nextElementSibling?.textContent.trim();
  }
  async function load(overrides: Record<string, unknown> = {}): Promise<void> {
    fixture.detectChanges();
    http
      .expectOne('/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3')
      .flush({ ...apiJob, ...overrides });
    await fixture.whenStable();
    http.match('/api/resumes/ai-models').forEach((request): void => {
      request.flush({ models: ['default-model', 'chosen-model'], warning: null });
    });
    http.match('/api/resumes/ai-settings').forEach((request): void => {
      request.flush({});
    });
    await fixture.whenStable();
  }
  async function enter(selector: string, value: string): Promise<void> {
    const field = element.querySelector<HTMLTextAreaElement>(selector);
    if (!field) {
      throw new Error(`Missing field ${selector}`);
    }
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }
  async function selectStatus(value: string): Promise<void> {
    const field = element.querySelector<HTMLSelectElement>('#application-status');
    if (!field) {
      throw new Error('Missing application status');
    }
    field.value = value;
    field.dispatchEvent(new Event('change', { bubbles: true }));
    await fixture.whenStable();
  }

  beforeEach(async (): Promise<void> => {
    route = new BehaviorSubject(
      convertToParamMap({ id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3' }),
    );
    query = new BehaviorSubject(convertToParamMap({}));
    await TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: route,
            queryParamMap: query,
          },
        },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobDetail);
    element = fixture.nativeElement as HTMLElement;
  });
  afterEach((): void => {
    http.match('/api/resumes/transcript').forEach((request): void => {
      if (!request.cancelled) {
        request.flush(null);
      }
    });
    fixture.destroy();
    http.verify();
  });

  it('saves the status', async (): Promise<void> => {
    await load();
    expect(element.querySelector('.save-application')).toBeNull();
    http.expectNone(`/api/jobs/${apiJob.id}/user`);
    const today = new Date();
    const appliedAt =
      new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12).getTime() / 1000;
    await selectStatus('applied');
    const request = http.expectOne(`/api/jobs/${apiJob.id}/user`);
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({
      status: 'applied',
      notes: '',
      applied_at: appliedAt,
      follow_up_at: null,
      version: 0,
    });
    expect(element.querySelector('.tracker .save-status')?.textContent).toContain('Saving');
    request.flush({ ...apiJob.user, status: 'applied', applied_at: appliedAt, version: 1 });
    await fixture.whenStable();
    expect(element.querySelector('.tracker .save-status')?.textContent).toContain('Saved');
    expect(element.querySelector<HTMLInputElement>('#applied-date')?.value).not.toBe('');
  });

  it('saves notes on blur', async (): Promise<void> => {
    await load();
    const appliedAt = new Date(2026, 8, 12, 12).getTime() / 1000;
    const followUpAt = new Date(2026, 8, 19, 12).getTime() / 1000;
    await enter('#applied-date', '2026-09-12');
    element.querySelector('#applied-date')?.dispatchEvent(new Event('change', { bubbles: true }));
    const applied = http.expectOne(`/api/jobs/${apiJob.id}/user`);
    expect(applied.request.body).toEqual({
      status: 'new',
      notes: '',
      applied_at: appliedAt,
      follow_up_at: null,
      version: 0,
    });
    applied.flush({ ...apiJob.user, applied_at: appliedAt, version: 1 });
    await fixture.whenStable();
    await enter('#follow-up', '2026-09-19');
    element.querySelector('#follow-up')?.dispatchEvent(new Event('change', { bubbles: true }));
    const followUp = http.expectOne(`/api/jobs/${apiJob.id}/user`);
    expect(followUp.request.body).toEqual({
      status: 'new',
      notes: '',
      applied_at: appliedAt,
      follow_up_at: followUpAt,
      version: 1,
    });
    followUp.flush({ ...apiJob.user, applied_at: appliedAt, follow_up_at: followUpAt, version: 2 });
    await fixture.whenStable();
    await enter('#application-notes', 'Contact the recruiter');
    http.expectNone(`/api/jobs/${apiJob.id}/user`);
    element.querySelector('#application-notes')?.dispatchEvent(new Event('blur'));
    const notes = http.expectOne(`/api/jobs/${apiJob.id}/user`);
    expect(notes.request.body).toEqual({
      status: 'new',
      notes: 'Contact the recruiter',
      applied_at: appliedAt,
      follow_up_at: followUpAt,
      version: 2,
    });
    notes.flush({
      ...apiJob.user,
      notes: 'Contact the recruiter',
      applied_at: appliedAt,
      follow_up_at: followUpAt,
      version: 3,
    });
    await fixture.whenStable();
  });

  it('keeps edits when saving fails', async (): Promise<void> => {
    await load();
    await selectStatus('saved');
    http
      .expectOne(`/api/jobs/${apiJob.id}/user`)
      .flush({}, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    expect(element.querySelector('.tracker .notice.error')?.textContent).toContain(
      'Your edits are preserved',
    );
    expect(element.querySelector<HTMLSelectElement>('#application-status')?.value).toBe('saved');
    button('Retry').click();
    const request = http.expectOne(`/api/jobs/${apiJob.id}/user`);
    expect(request.request.body).toEqual({
      status: 'saved',
      notes: '',
      applied_at: null,
      follow_up_at: null,
      version: 0,
    });
    request.flush({ ...apiJob.user, status: 'saved', version: 1 });
    await fixture.whenStable();
    expect(element.querySelector('.tracker .notice.error')).toBeNull();
  });

  it('checks if the posting is open', async (): Promise<void> => {
    await load({ application_url: 'https://example.com/jobs/1' });
    expect(element.querySelector('.closed-panel')).toBeNull();
    button('Check if open').click();
    await fixture.whenStable();
    expect(button('Checking…').disabled).toBe(true);
    const checkedAt = Date.UTC(2026, 9, 22, 15) / 1000;
    const request = http.expectOne(`/api/jobs/${apiJob.id}/check-link`);
    expect(request.request.method).toBe('POST');
    request.flush({
      ...apiJob,
      application_url: 'https://example.com/jobs/1',
      details_version: 4,
      active: false,
      closed_at: checkedAt,
      closed_reason: 'link_check',
      closed_detail: 'The posting page no longer exists (HTTP 404).',
      link_check: {
        checked_at: checkedAt,
        status: 'closed',
        detail: 'The posting page no longer exists (HTTP 404).',
        url: 'https://example.com/jobs/1',
        final_url: null,
      },
    });
    await fixture.whenStable();
    expect(element.textContent).toContain('Closed. The posting page no longer exists (HTTP 404).');
    const panel = element.querySelector('.closed-panel');
    expect(panel?.textContent).toContain('This posting looks closed');
    expect(panel?.textContent).toContain('The posting page no longer exists (HTTP 404).');
    expect(stat('Posting status')).toBe('Closed');
    expect(stat('Last link check')).toContain('Closed');
    expect(button('Check if open').disabled).toBe(false);
  });

  it('shows cleaned text', async (): Promise<void> => {
    const raw =
      '<style>.banner { color: red; }</style><p>Build tools.</p><script>alert(1)</script>';
    await load({ raw_description: raw, cleaned_description: 'Build tools.' });
    expect(element.querySelector('#job-description-text')?.textContent).toBe('Build tools.');
    const reference = element.querySelector('.raw-description');
    expect(reference?.querySelector('.full-description')?.textContent).toBe(raw);
    expect(reference?.querySelector('style, script, .banner')).toBeNull();
    button('Edit description').click();
    await fixture.whenStable();
    expect(element.querySelector<HTMLTextAreaElement>('#edit-description')?.value).toBe(
      'Build tools.',
    );
    expect(element.querySelector<HTMLTextAreaElement>('#edit-raw-description')?.value).toBe(raw);
    await enter('#edit-description', 'Build accessible tools.');
    await enter('#edit-raw-description', '<p>Build accessible tools.</p>');
    button('Save description').click();
    const request = http.expectOne(`/api/jobs/${apiJob.id}`);
    expect(request.request.body).toEqual({
      version: 3,
      raw_description: '<p>Build accessible tools.</p>',
      cleaned_description: 'Build accessible tools.',
    });
    request.flush({
      ...apiJob,
      raw_description: '<p>Build accessible tools.</p>',
      cleaned_description: 'Build accessible tools.',
      details_version: 4,
    });
    await fixture.whenStable();
    expect(element.querySelector('#job-description-text')?.textContent).toBe(
      'Build accessible tools.',
    );
    expect(element.querySelector('.raw-description .full-description')?.textContent).toBe(
      '<p>Build accessible tools.</p>',
    );
  });
});
