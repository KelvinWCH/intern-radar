import { Location } from '@angular/common';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Tailor } from './tailor';

const generated = {
  name: 'Alex Example',
  email: 'alex@example.com',
  phone: null,
  location: 'Toronto',
  links: [],
  education: [
    {
      institution: 'Example University',
      degree: 'BSc',
      field_of_study: 'Computer Science',
      location: null,
      start_date: '2023',
      end_date: '2027',
      bullets: [],
    },
  ],
  experience: [
    {
      company: 'Example Studio',
      title: 'Developer',
      location: null,
      start_date: '2025',
      end_date: null,
      bullets: ['Built a tested API for a student project.'],
    },
  ],
  projects: [],
  skills: [{ category: 'Languages', items: ['TypeScript', 'Python'] }],
  additional_sections: [],
};

const job = {
  id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
  source_type: 'user_added',
  company: 'Example',
  title: 'Developer',
  application_url: 'https://example.com/jobs/7',
  apply_url: null,
  raw_description: 'Build tools. Use Python.',
  locations: [],
  terms: [],
  category: null,
  summary: null,
  first_seen_at: 1792238400,
  date_posted: Date.UTC(2026, 9, 16) / 1000,
};
const document = {
  id: '11111111-1111-4111-8111-111111111111',
  job_id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
  company: 'Example',
  title: 'Developer',
  status: 'completed',
  created_at: 1792238400,
  finished_at: 1792238420,
  has_resume: true,
  has_cover_letter: true,
  error: null,
  profile_revision: 1,
  job_description: job.raw_description,
  resume: generated,
  cover_letter: {
    name: 'Alex Example',
    email: null,
    phone: null,
    location: null,
    links: [],
    company: 'Example',
    job_title: 'Developer',
    greeting: 'Dear Hiring Team,',
    paragraphs: ['I build useful tools.'],
    closing: 'Sincerely,',
  },
};

describe('Tailor', (): void => {
  let fixture: ComponentFixture<Tailor>;
  let element: HTMLElement;
  let http: HttpTestingController;

  function button(label: string): HTMLButtonElement {
    const result = Array.from(element.querySelectorAll('button')).find(
      (candidate): boolean => candidate.textContent.trim() === label,
    );
    if (!result) {
      throw new Error(`Missing button: ${label}`);
    }
    return result;
  }

  async function enterDescription(
    description = 'Build Angular tools and Python APIs.',
  ): Promise<void> {
    const input = element.querySelector('textarea');
    if (!input) {
      throw new Error('Missing job description input.');
    }
    input.value = description;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }

  async function chooseFile(file: File): Promise<void> {
    const input = element.querySelector<HTMLInputElement>('input[type=file]');
    if (!input) {
      throw new Error('Missing source file input.');
    }
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: { item: (): File => file },
    });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await fixture.whenStable();
  }

  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [Tailor],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Tailor);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    http.match('/api/resumes/ai-models').forEach((request): void => {
      request.flush({ models: ['default-model', 'chosen-model'], warning: null });
    });
    http.match('/api/resumes/ai-settings').forEach((request): void => {
      request.flush({});
    });
  });

  afterEach((): void => {
    fixture.destroy();
    http.verify();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('tailors a manual job', async (): Promise<void> => {
    expect(element.querySelector('.tailor-steps .current')?.textContent).toContain('Prepare');
    const address = vi.spyOn(TestBed.inject(Location), 'replaceState');
    http.expectOne('/api/resumes/profile').flush({}, { status: 404, statusText: 'Not found' });
    await fixture.whenStable();
    expect(element.querySelector<HTMLDetailsElement>('.job-details')?.open).toBe(true);
    expect(element.querySelector<HTMLDetailsElement>('.advanced-settings')?.open).toBe(false);
    await enterDescription();
    expect(button('Research & tailor').disabled).toBe(true);
    await chooseFile(new File(['Alex Example'], 'resume.txt', { type: 'text/plain' }));
    button('Save resume').click();
    const upload = http.expectOne('/api/resumes/upload');
    expect(upload.request.body).toBeInstanceOf(FormData);
    upload.flush({ name: 'Alex Example' });
    await fixture.whenStable();
    const posted = element.querySelector<HTMLInputElement>('#target-date-posted');
    if (!posted) {
      throw new Error('Missing date posted input');
    }
    posted.value = '2026-10-16';
    posted.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
    button('Research & tailor').click();
    const save = http.expectOne('/api/jobs/for-tailoring');
    expect(save.request.body).toEqual({
      company: 'Not specified',
      title: 'Not specified',
      raw_description: 'Build Angular tools and Python APIs.',
      application_url: null,
      date_posted: Date.UTC(2026, 9, 16) / 1000,
    });
    save.flush(job);
    expect(address).toHaveBeenLastCalledWith(`/tailor?job=${job.id}`);
    const request = http.expectOne(
      '/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks',
    );
    expect(request.request.body).toMatchObject({
      include_resume: true,
      include_cover_letter: true,
    });
    await fixture.whenStable();
    expect(button('Generating documents…').disabled).toBe(true);
    expect(element.querySelector('.tailor-steps .current')?.textContent).toContain(
      'Research & write',
    );
    const consolePanel = element.querySelector('app-tailoring-console');
    expect(consolePanel?.closest('.output-panel')).toBeNull();
    expect(consolePanel?.textContent).toContain('Connecting');
    request.flush(document);
    await fixture.whenStable();
    expect(element.querySelector('.tailor-steps .current')?.textContent).toContain(
      'Review & download',
    );
    expect(element.querySelector('app-tailoring-console')).toBe(consolePanel);
    expect(element.querySelector('app-resume-preview')?.textContent).toContain(
      'Built a tested API',
    );
    expect(element.querySelector('app-cover-letter-preview')?.textContent).toContain(
      'I build useful tools.',
    );
    expect(
      element.querySelector('a[href="/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3"]'),
    ).not.toBeNull();
    expect(
      element.querySelector(
        `a[href="/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3?version=${document.id}"]`,
      ),
    ).not.toBeNull();
    http.expectNone('/api/resumes/generate');
  });

  it('reuses the request id', async (): Promise<void> => {
    http.expectOne('/api/resumes/profile').flush({ name: 'Alex Example' });
    await fixture.whenStable();
    await enterDescription();
    button('Research & tailor').click();
    http.expectOne('/api/jobs/for-tailoring').flush(job);
    const request = http.expectOne(
      '/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks',
    );
    const original: unknown = request.request.body;
    request.error(new ProgressEvent('network'));
    await fixture.whenStable();
    expect(element.querySelector('textarea')?.value).toContain('Build Angular');
    button('Research & tailor').click();
    const retry = http.expectOne('/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks');
    expect(retry.request.body).toEqual(original);
    retry.flush(document);
    await fixture.whenStable();
    http.expectNone('/api/jobs/for-tailoring');
  });

  it('rejects bad uploads', async (): Promise<void> => {
    http.expectOne('/api/resumes/profile').flush({}, { status: 404, statusText: 'Not found' });
    await fixture.whenStable();
    await chooseFile(new File(['test'], 'resume.exe'));
    expect(button('Save resume').disabled).toBe(true);
    await chooseFile(new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'resume.txt'));
    expect(button('Save resume').disabled).toBe(true);
    http.expectNone('/api/resumes/upload');
  });

  it('rejects bad output', async (): Promise<void> => {
    http.expectOne('/api/resumes/profile').flush({ name: 'Alex Example' });
    await fixture.whenStable();
    await enterDescription();
    button('Research & tailor').click();
    http.expectOne('/api/jobs/for-tailoring').flush(job);
    http
      .expectOne('/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks')
      .flush({ ...document, resume: { ...generated, experience: 'invalid' } });
    await fixture.whenStable();
    expect(element.querySelector('app-resume-preview')).toBeNull();
    expect(element.textContent).toContain('Could not complete tailoring');
    http.expectNone('/api/resumes/latex');
  });
});
