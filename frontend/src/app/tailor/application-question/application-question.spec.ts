import { Clipboard } from '@angular/cdk/clipboard';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import type { JobSummary } from '../../jobs/models/job.models';
import { ApplicationQuestion } from './application-question';

const job: JobSummary = {
  id: 'job-1',
  sourceType: 'user_added',
  company: 'Example',
  title: 'Engineering Intern',
  rawDescription: 'Build accessible tools using TypeScript.',
  applicationUrl: 'https://example.com/jobs/1',
  applyUrl: 'https://example.com/apply/1',
  locations: ['Toronto'],
  terms: [],
  category: null,
  summary: null,
  firstSeenAt: 1,
  user: {
    status: 'saved',
    notes: '',
    applied_at: null,
    follow_up_at: null,
    updated_at: null,
    version: 0,
    documents: [],
  },
};

describe('ApplicationQuestion', (): void => {
  let fixture: ComponentFixture<ApplicationQuestion>;
  let element: HTMLElement;
  let http: HttpTestingController;

  async function enter(selector: string, value: string): Promise<void> {
    const field = element.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    if (!field) {
      throw new Error(`Missing field ${selector}`);
    }
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }

  function submit(): HTMLButtonElement {
    const button = element.querySelector<HTMLButtonElement>('button[type=submit]');
    if (!button) {
      throw new Error('Missing draft button');
    }
    return button;
  }

  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [ApplicationQuestion],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(ApplicationQuestion);
    fixture.componentRef.setInput('job', job);
    element = fixture.nativeElement as HTMLElement;
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  afterEach((): void => {
    fixture.destroy();
    http.verify();
    vi.restoreAllMocks();
  });

  it('drafts an answer', async (): Promise<void> => {
    expect(element.querySelector('.answer-output')?.textContent).toContain(
      'Your draft will appear here.',
    );
    await enter('#application-question', '  Why this role?  ');
    await enter('#answer-word-limit', '100');
    await enter('#answer-context', '  I enjoy building useful tools.  ');
    submit().click();
    const request = http.expectOne('/api/resumes/questions/answer');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      question: 'Why this role?',
      max_words: 100,
      ai_options: { reasoning_effort: 'medium' },
      additional_context: 'I enjoy building useful tools.',
      job: {
        company: 'Example',
        title: 'Engineering Intern',
        raw_description: 'Build accessible tools using TypeScript.',
        application_url: 'https://example.com/jobs/1',
      },
    });
    await fixture.whenStable();
    expect(submit().disabled).toBe(true);
    expect(element.querySelector('fieldset')?.disabled).toBe(true);
    expect(element.querySelector('.answer-output')?.textContent).toContain(
      'Writing and checking your draft',
    );
    request.flush({
      question: 'Why this role?',
      answer: 'I build useful tools.',
      missing_information: [],
      word_count: 4,
    });
    await fixture.whenStable();
    expect(element.querySelector<HTMLTextAreaElement>('#application-answer')?.value).toBe(
      'I build useful tools.',
    );
    expect(element.textContent).toContain('4 / 100 words');
    expect(element.querySelector('.answer-empty')).toBeNull();
    await enter('#application-answer', 'I build accessible tools for everyone.');
    const copy = vi.spyOn(TestBed.inject(Clipboard), 'copy').mockReturnValue(true);
    const copyButton = Array.from(element.querySelectorAll('button')).find((button): boolean =>
      button.textContent.includes('Copy answer'),
    );
    copyButton?.click();
    await fixture.whenStable();
    expect(copy).toHaveBeenCalledWith('I build accessible tools for everyone.');
    expect(element.textContent).toContain('6 / 100 words');
    expect(element.textContent).toContain('Copied. Ready for your application.');
    await enter('#application-answer', 'A revised answer.');
    expect(element.textContent).not.toContain('Copied. Ready for your application.');
    http.expectNone('/api/jobs/job-1/user');
  });

  it('shows missing facts', async (): Promise<void> => {
    await enter('#application-question', 'When can you start?');
    submit().click();
    http.expectOne('/api/resumes/questions/answer').flush({
      question: 'When can you start?',
      answer: null,
      missing_information: ['Your earliest available start date.'],
      word_count: 0,
    });
    await fixture.whenStable();
    expect(element.textContent).toContain('Your earliest available start date.');
    expect(element.querySelector('#application-answer')).toBeNull();
    expect(submit().disabled).toBe(false);
    await enter('#answer-context', 'I can start on May 3, 2027.');
    submit().click();
    const retry = http.expectOne('/api/resumes/questions/answer');
    expect(retry.request.body).toMatchObject({
      additional_context: 'I can start on May 3, 2027.',
    });
    retry.flush({
      question: 'When can you start?',
      answer: 'I can start on May 3, 2027.',
      missing_information: [],
      word_count: 7,
    });
    await fixture.whenStable();
    expect(element.querySelector('.missing-information')).toBeNull();
    expect(element.querySelector('#application-answer')).not.toBeNull();
  });
});
