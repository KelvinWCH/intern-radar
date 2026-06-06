import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ApplicationReview, PdfDiagnostics } from '../models/application-review.models';
import { parseApplicationReview, parsePdfDiagnostics } from '../models/application-review.models';
import { ApplicationReviewPanel } from './application-review';

const review: ApplicationReview = {
  status: 'needs_attention',
  decisions: [],
  revised_documents: ['resume'],
  passes: [
    {
      round: 2,
      acknowledged_finding_indices: [],
      analysis: {
        summary: 'Check the remaining claim.',
        gaps: [],
        findings: [
          {
            document: 'resume',
            category: 'grounding',
            severity: 'error',
            draft_quote: '<script>not executable</script>',
            issue: 'The metric is unsupported.',
            recommendation: 'Keep the source qualifier.',
          },
        ],
      },
      document_hashes: { resume: 'a'.repeat(64) },
      ai_usage: null,
    },
  ],
};
const diagnostics: PdfDiagnostics = {
  document: 'resume',
  document_sha256: 'a'.repeat(64),
  pdf_sha256: 'b'.repeat(64),
  page_count: 1,
  extracted_text: 'Alex\nEducation\n<raw text>',
  checks: [
    {
      key: 'identity',
      label: 'Contact details',
      status: 'warning',
      detail: 'Email is missing.',
      missing: ['alex@example.com'],
    },
  ],
  matched_required_skills: ['Python'],
  missing_supported_skills: ['Redis'],
  unsupported_required_skills: ['Kubernetes'],
  matched_keywords: ['Python'],
  missing_supported_keywords: ['Redis'],
  unsupported_keywords: ['Kubernetes'],
};

describe('Application review reports', (): void => {
  beforeEach((): void => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
  });
  it('requires a choice', async (): Promise<void> => {
    const fixture = TestBed.createComponent(ApplicationReviewPanel);
    fixture.componentRef.setInput('report', { ...review, status: 'awaiting_decision' });
    fixture.componentRef.setInput('canDecide', true);
    fixture.componentRef.setInput('documentId', 'first-document');
    const submitted = vi.fn();
    fixture.componentInstance.decision.subscribe(submitted);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    const submit = element.querySelector<HTMLButtonElement>('.decision-actions button');
    expect(submit?.disabled).toBe(true);
    expect(element.querySelector('input:checked')).toBeNull();
    const revise = element.querySelectorAll<HTMLInputElement>('input[type="radio"]')[1];
    revise?.click();
    await fixture.whenStable();
    const guidance = element.querySelector('textarea');
    if (!guidance) {
      throw new Error('Missing revision guidance');
    }
    guidance.value = 'Preserve the source qualifier.';
    guidance.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(submit?.disabled).toBe(false);
    fixture.componentRef.setInput('report', { ...review, status: 'awaiting_decision' });
    await fixture.whenStable();
    expect(submit?.disabled).toBe(false);
    expect(guidance.value).toBe('Preserve the source qualifier.');
    submit?.click();
    expect(submitted).toHaveBeenCalledWith({
      round: 2,
      decisions: [
        { finding_index: 0, action: 'revise', guidance: 'Preserve the source qualifier.' },
      ],
    });
    fixture.componentRef.setInput('saving', true);
    await fixture.whenStable();
    expect(submit?.disabled).toBe(true);
    fixture.componentRef.setInput('report', {
      ...review,
      status: 'awaiting_decision',
      passes: review.passes.map((pass) => ({ ...pass, round: 3 })),
    });
    fixture.componentRef.setInput('saving', false);
    await fixture.whenStable();
    expect(submit?.disabled).toBe(true);
    expect(element.querySelector('input:checked')).toBeNull();
    element.querySelector<HTMLInputElement>('input[type="radio"]')?.click();
    await fixture.whenStable();
    submit?.click();
    expect(submitted).toHaveBeenLastCalledWith({
      round: 3,
      decisions: [{ finding_index: 0, action: 'keep', guidance: '' }],
    });
    fixture.componentRef.setInput('documentId', 'another-document');
    await fixture.whenStable();
    expect(submit?.disabled).toBe(true);
    expect(element.querySelector('input:checked')).toBeNull();
    element.querySelectorAll<HTMLInputElement>('input[type="radio"]')[1]?.click();
    await fixture.whenStable();
    expect(element.querySelector('textarea')?.value).toBe('');
    fixture.destroy();
  });

  it('rejects bad review data', (): void => {
    expect(parseApplicationReview(review)).toEqual(review);
    expect(parsePdfDiagnostics(diagnostics)).toEqual(diagnostics);
    expect(() => parseApplicationReview({ ...review, status: 'approved' })).toThrow();
    for (const indices of [[-1], [0.5], [1], ['0'], [0, 0]]) {
      expect(() =>
        parseApplicationReview({
          ...review,
          passes: review.passes.map((pass) => ({
            ...pass,
            acknowledged_finding_indices: indices,
          })),
        }),
      ).toThrow();
    }
    expect(() =>
      parseApplicationReview({
        ...review,
        passes: review.passes.map((pass) => ({
          ...pass,
          acknowledged_finding_indices: [0],
          analysis: {
            ...pass.analysis,
            findings: pass.analysis.findings.map((finding) => ({
              ...finding,
              severity: 'suggestion',
            })),
          },
        })),
      }),
    ).toThrow();
    expect(() => parsePdfDiagnostics({ ...diagnostics, page_count: 1.5 })).toThrow();
    expect(() => parsePdfDiagnostics({ ...diagnostics, pdf_sha256: 'not a digest' })).toThrow();
    expect(() =>
      parsePdfDiagnostics({
        ...diagnostics,
        checks: [{ ...diagnostics.checks[0], status: 'approved' }],
      }),
    ).toThrow();
  });
});
