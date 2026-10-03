import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AddJob } from './add-job';

describe('AddJob', (): void => {
  let fixture: ComponentFixture<AddJob>;
  let element: HTMLElement;
  let http: HttpTestingController;

  async function enter(selector: string, text: string): Promise<void> {
    const input = element.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    if (!input) {
      throw new Error('Missing form field.');
    }
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }

  function saveButton(): HTMLButtonElement {
    const button = element.querySelector<HTMLButtonElement>('button[type=submit]');
    if (!button) {
      throw new Error('Missing save button.');
    }
    return button;
  }

  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [AddJob],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AddJob);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    await fixture.whenStable();
  });

  afterEach((): void => {
    fixture.destroy();
    http.verify();
  });

  it('saves a job without a url', async (): Promise<void> => {
    expect(saveButton().disabled).toBe(true);
    await enter('textarea', '  Build useful tools.  ');
    saveButton().click();
    const request = http.expectOne('/api/jobs');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      company: 'Not specified',
      title: 'Not specified',
      application_url: null,
      raw_description: 'Build useful tools.',
    });
    await fixture.whenStable();
    expect(saveButton().disabled).toBe(true);
    request.flush({
      user: {
        status: 'new',
        notes: '',
        applied_at: null,
        follow_up_at: null,
        updated_at: null,
        version: 0,
        documents: [],
      },
      id: '7',
      source_type: 'user_added',
      company: 'Not specified',
      title: 'Not specified',
      application_url: null,
      apply_url: null,
      raw_description: 'Build useful tools.',
      locations: [],
      terms: [],
      category: null,
      summary: null,
      first_seen_at: 1792238400,
    });
    await fixture.whenStable();
    expect(element.textContent).toContain('Job saved in your workspace');
    expect(element.querySelector('a[href="/jobs/7"]')).not.toBeNull();
    expect(element.querySelector('textarea')?.value).toBe('');
    expect(saveButton().disabled).toBe(true);
  });

  it('rejects blank descriptions and bad links', async (): Promise<void> => {
    await enter('textarea', '   ');
    expect(saveButton().disabled).toBe(true);
    await enter('textarea', 'Build tools.');
    await enter('#new-url', 'javascript:alert(1)');
    expect(saveButton().disabled).toBe(true);
    await enter('#new-url', 'https://example.com/jobs/1');
    expect(saveButton().disabled).toBe(false);
    http.expectNone('/api/jobs');
  });
});
