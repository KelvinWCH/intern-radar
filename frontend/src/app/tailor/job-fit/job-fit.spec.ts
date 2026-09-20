import { TestBed } from '@angular/core/testing';
import { parsePdfDiagnostics } from '../models/application-review.models';
import { JobFit } from './job-fit';

describe('Job fit report', (): void => {
  it('lists covered requirements before gaps', async (): Promise<void> => {
    const fixture = TestBed.createComponent(JobFit);
    fixture.componentRef.setInput('coverage', [
      { requirement: 'Kubernetes', importance: 'preferred', entries: [] },
      { requirement: 'Build Python APIs', importance: 'required', entries: ['Intern, Example'] },
    ]);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    const items = [...element.querySelectorAll('.coverage li')];
    expect(items.map((item) => item.getAttribute('data-covered'))).toEqual(['true', 'false']);
    expect(items[0]?.textContent).toContain('Shown in Intern, Example');
    expect(items[1]?.textContent).toContain('No supporting entry in your profile');
  });

  it('shows keyword matches', async (): Promise<void> => {
    const fixture = TestBed.createComponent(JobFit);
    fixture.componentRef.setInput(
      'checks',
      parsePdfDiagnostics({
        document: 'resume',
        document_sha256: 'a'.repeat(64),
        pdf_sha256: 'b'.repeat(64),
        page_count: 1,
        extracted_text: 'Alex',
        checks: [],
        matched_required_skills: [],
        missing_supported_skills: [],
        unsupported_required_skills: [],
        matched_keywords: ['Python'],
        missing_supported_keywords: ['pytest'],
        unsupported_keywords: ['Kubernetes'],
      }),
    );
    await fixture.whenStable();
    const items = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.keywords li')];
    expect(items.map((item) => item.getAttribute('data-state'))).toEqual([
      'used',
      'missing',
      'gap',
    ]);
    expect(items[1]?.textContent).toContain('supported, not used');
  });
});
