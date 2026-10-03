import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { parseJob } from '../models/job.models';
import { JobEditor } from './job-editor';

const apiJob = {
  id: '7',
  source_type: 'scraped',
  details_version: 3,
  company: 'Example',
  title: 'Intern',
  application_url: 'https://example.com/job',
  apply_url: null,
  company_url: null,
  source_job_id: 'REQ-1',
  raw_description: 'Original description',
  cleaned_description: 'Cleaned description',
  locations: ['Toronto'],
  terms: ['Summer 2027'],
  category: null,
  summary: null,
  sponsorship: null,
  active: true,
  date_posted: 1792238400,
  date_updated: null,
  qualifications: null,
  first_seen_at: 1792238400,
  user: {
    status: 'saved',
    notes: 'Keep notes',
    applied_at: null,
    follow_up_at: null,
    updated_at: null,
    version: 2,
    documents: [],
  },
};

describe('JobEditor', (): void => {
  let fixture: ComponentFixture<JobEditor>;
  let http: HttpTestingController;
  let element: HTMLElement;

  function button(text: string): HTMLButtonElement {
    const found = Array.from(element.querySelectorAll('button')).find((item): boolean =>
      item.textContent.includes(text),
    );
    if (!found) {
      throw new Error(`Missing button ${text}`);
    }
    return found;
  }
  async function enter(selector: string, value: string): Promise<void> {
    const field = element.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    if (!field) {
      throw new Error('Missing field');
    }
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }
  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(JobEditor);
    fixture.componentRef.setInput('job', parseJob(apiJob));
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    button('Edit job details').click();
    await fixture.whenStable();
  });
  afterEach((): void => {
    fixture.destroy();
    http.verify();
  });

  it('sends only changed fields', async (): Promise<void> => {
    const saved = vi.fn();
    fixture.componentInstance.saved.subscribe(saved);
    await enter('#new-title', 'Corrected role');
    await enter('#new-url', '');
    button('Save job details').click();
    const request = http.expectOne('/api/jobs/7');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({
      version: 3,
      title: 'Corrected role',
      application_url: null,
    });
    request.flush({
      ...apiJob,
      title: 'Corrected role',
      application_url: null,
      details_version: 4,
    });
    await fixture.whenStable();
    expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Corrected role', detailsVersion: 4 }),
    );
    expect(element.textContent).toContain('Job details saved');
    expect(element.querySelector('textarea')).toBeNull();
  });

  it('validates and cancels', async (): Promise<void> => {
    await enter('#new-company', '   ');
    expect(button('Save job details').disabled).toBe(true);
    await enter('#new-company', 'Changed');
    await enter('#job-apply_url', 'javascript:alert(1)');
    expect(button('Save job details').disabled).toBe(true);
    button('Cancel edits').click();
    await fixture.whenStable();
    button('Edit job details').click();
    await fixture.whenStable();
    expect(element.querySelector<HTMLInputElement>('#new-company')?.value).toBe('Example');
    http.expectNone('/api/jobs/7');
  });
});
