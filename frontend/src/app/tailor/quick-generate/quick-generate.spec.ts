import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import type { TailorRequest } from '../models/document.models';
import { QuickGenerate } from './quick-generate';

const startedAt = 1792238400;
const job = {
  id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
  company: 'Example',
  title: 'Engineer',
};
const accepted = {
  id: '00000000-0000-4000-8000-000000000001',
  job_id: job.id,
  company: job.company,
  title: job.title,
  status: 'running',
  created_at: startedAt,
  finished_at: null,
  has_resume: false,
  has_cover_letter: false,
  error: null,
  profile_revision: 1,
  job_description: 'Build APIs',
  resume: null,
  cover_letter: null,
  events: [{ id: 1, created_at: startedAt, stage: 'queued', message: 'Accepted' }],
};
const submitUrl = `/api/jobs/${job.id}/tailor-tasks`;

describe('QuickGenerate', (): void => {
  let fixture: ComponentFixture<QuickGenerate>;
  let element: HTMLElement;
  let http: HttpTestingController;

  function render(): void {
    TestBed.tick();
    fixture.detectChanges();
  }

  function control(): HTMLElement {
    const found = element.querySelector<HTMLElement>('.quick-generate');
    if (!found) {
      throw new Error('Quick generate control missing');
    }
    return found;
  }

  beforeEach((): void => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [QuickGenerate],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(QuickGenerate);
    fixture.componentRef.setInput('job', job);
    element = fixture.nativeElement as HTMLElement;
    render();
  });

  afterEach((): void => {
    fixture.destroy();
    http.verify();
    vi.useRealTimers();
  });

  it('starts a run and links to the documents', (): void => {
    expect(control().textContent).toContain('Quick generate');
    control().click();
    const submit = http.expectOne(submitUrl);
    expect(submit.request.body).toMatchObject({
      mode: 'one_shot',
      include_resume: true,
      include_cover_letter: true,
    });
    render();
    expect(control().textContent).toContain('Starting...');

    submit.flush(accepted);
    render();
    expect(control().getAttribute('href')).toBe(`/jobs/${job.id}?version=${accepted.id}`);
    expect(control().textContent).toContain('Generating...');

    vi.advanceTimersByTime(5000);
    http
      .expectOne(`/api/documents/${accepted.id}`)
      .flush({ ...accepted, status: 'completed', finished_at: startedAt + 300 });
    render();
    expect(control().textContent).toContain('Documents ready');
  });

  it('shows the error and retries', (): void => {
    control().click();
    const first = http.expectOne(submitUrl);
    first.flush(
      { detail: 'Save a source resume before tailoring' },
      { status: 409, statusText: 'Conflict' },
    );
    render();
    expect(element.querySelector('.quick-error')?.textContent).toContain(
      'Save a source resume before tailoring',
    );
    expect(control().textContent).toContain('Retry');

    control().click();
    const retry = http.expectOne(submitUrl);
    expect((retry.request.body as TailorRequest).request_id).not.toBe(
      (first.request.body as TailorRequest).request_id,
    );
    retry.flush(accepted);
    render();
    expect(element.querySelector('.quick-error')).toBeNull();
    expect(control().textContent).toContain('Generating');
  });
});
