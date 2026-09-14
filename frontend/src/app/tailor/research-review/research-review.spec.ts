import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import type { DocumentDetail } from '../models/document.models';
import { parseDocument } from '../models/document.models';
import { ResearchReview } from './research-review';

const pending = parseDocument({
  id: '11111111-1111-4111-8111-111111111111',
  job_id: 'job-1',
  company: 'Example',
  title: 'Engineer',
  status: 'awaiting_review',
  created_at: 100,
  finished_at: null,
  has_resume: false,
  has_cover_letter: false,
  error: null,
  profile_revision: 1,
  job_description: 'Build APIs',
  resume: null,
  cover_letter: null,
  research: {
    validated: false,
    revision: 1,
    approved_at: null,
    validation_issues: ['Company mission: the quote was not found in source 1.'],
    sources: [{ title: 'Job description', url: null, text: 'Build APIs' }],
    warnings: [],
    analysis: {
      mission: { finding: 'Build APIs', source_index: 0, quote: 'Invented quote' },
      company_context: [],
      role_priorities: [],
      requirements: [],
      tailoring_guidance: [],
      unknowns: [],
    },
  },
});

describe('Research review', (): void => {
  let fixture: ComponentFixture<ResearchReview>;
  let http: HttpTestingController;
  let element: HTMLElement;
  const url = `/api/documents/${pending.id}/research-review`;

  beforeEach(async (): Promise<void> => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(ResearchReview);
    fixture.componentRef.setInput('document', pending);
    http = TestBed.inject(HttpTestingController);
    element = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });
  afterEach((): void => {
    http.verify();
  });

  function button(label: string): HTMLButtonElement {
    const found = Array.from(element.querySelectorAll('button')).find(
      (button) => button.textContent.trim() === label,
    );
    if (!found) {
      throw new Error(`Missing button: ${label}`);
    }
    return found;
  }

  it('waits for continue', (): void => {
    expect(element.textContent).toContain('Writing is paused');
    expect(element.textContent).toContain('the quote was not found');
    http.expectNone(url);
    let result: DocumentDetail | undefined;
    fixture.componentInstance.updated.subscribe((document): void => {
      result = document;
    });
    button('Continue with unverified research').click();
    button('Continue with unverified research').click();
    const request = http.expectOne(url);
    expect(request.request.body).toEqual({ action: 'continue', revision: 1 });
    request.flush({ ...pending, status: 'running' });
    expect(result?.status).toBe('running');
    http.expectNone(url);
  });

  it('saves edited findings', async (): Promise<void> => {
    fixture.componentInstance.updated.subscribe((document): void => {
      fixture.componentRef.setInput('document', document);
    });
    button('Edit report').click();
    await fixture.whenStable();
    const quote = element.querySelector<HTMLTextAreaElement>('[name="missionQuote"]');
    if (!quote) {
      throw new Error('Missing quote input');
    }
    quote.value = 'Build APIs';
    quote.dispatchEvent(new Event('input'));
    const knowledge = element.querySelector<HTMLTextAreaElement>('[name="companyKnowledge"]');
    if (!knowledge) {
      throw new Error('Missing company knowledge input');
    }
    knowledge.value = 'Runs a marketplace\n\n  Serves small shops  ';
    knowledge.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button('Save edits & check citations').click();
    const request = http.expectOne(url);
    expect(request.request.body).toMatchObject({
      action: 'save',
      revision: 1,
      analysis: {
        mission: { quote: 'Build APIs' },
        company_knowledge: ['Runs a marketplace', 'Serves small shops'],
      },
    });
    expect(pending.research?.analysis.mission?.quote).toBe('Invented quote');
    request.flush({
      ...pending,
      research: { ...pending.research, validated: true, revision: 2, validation_issues: [] },
    });
    await fixture.whenStable();
    expect(element.textContent).toContain('citations now match');
    http.expectNone(url);
    button('Continue with this report').click();
    const continuation = http.expectOne(url);
    expect(continuation.request.body).toEqual({ action: 'continue', revision: 2 });
    continuation.flush({ ...pending, status: 'running' });
  });
});
