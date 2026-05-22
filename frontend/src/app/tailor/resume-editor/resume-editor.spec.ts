import { provideHttpClient } from '@angular/common/http';
import type { TestRequest } from '@angular/common/http/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { ResumeEditor } from './resume-editor';

const documentId = '00000000-0000-4000-8000-000000000001';

const resume = {
  ai_usage: null,
  requirement_coverage: [
    { requirement: 'Build Python APIs', importance: 'required', entries: ['Software Intern'] },
  ],
  name: 'Alex Example',
  email: 'alex@example.com',
  phone: null,
  location: 'Toronto, ON',
  linkedin: null,
  github: null,
  links: [],
  education: [],
  experience: [
    {
      company: 'Example Co',
      title: 'Software Intern',
      location: null,
      start_date: null,
      end_date: null,
      bullets: ['Built Python APIs used by 40 clinics'],
    },
  ],
  projects: [],
  skills: [{ category: 'Languages', items: ['Python'] }],
  additional_sections: [],
};

const attempt = {
  id: documentId,
  job_id: 'listing-1',
  company: 'Example Co',
  title: 'Backend Intern',
  status: 'completed',
  created_at: 100,
  finished_at: 200,
  has_resume: true,
  has_cover_letter: false,
  error: null,
  profile_revision: 1,
  job_description: 'Build Python APIs.',
  resume,
  generated_resume: null,
  resume_edited_at: null,
  resume_revision: 0,
  cover_letter: null,
};

function preview(pages = 1, overflow = 0, bullets: unknown[] = []): Record<string, unknown> {
  return {
    pdf_base64: btoa('%PDF-1.7 preview'),
    page_count: pages,
    overflow_lines: overflow,
    blank_inches: 0,
    bullets,
    fitted: [],
  };
}

describe('ResumeEditor', (): void => {
  let fixture: ComponentFixture<ResumeEditor>;
  let http: HttpTestingController;
  let element: HTMLElement;

  function button(label: string): HTMLButtonElement {
    const found = Array.from(element.querySelectorAll('button')).find((item): boolean =>
      item.textContent.includes(label),
    );
    if (!found) {
      throw new Error(`Missing button ${label}`);
    }
    return found;
  }
  function enter(selector: string, value: string): void {
    const field = element.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    if (!field) {
      throw new Error(`Missing field ${selector}`);
    }
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
  function previewRequest(): TestRequest {
    return http.expectOne({ method: 'POST', url: '/api/resumes/draft-preview' });
  }
  async function open(overrides: Record<string, unknown> = {}): Promise<void> {
    fixture.detectChanges();
    http.expectOne(`/api/documents/${documentId}`).flush({ ...attempt, ...overrides });
    fixture.detectChanges();
    await vi.advanceTimersByTimeAsync(0);
  }

  beforeEach(async (): Promise<void> => {
    vi.useFakeTimers();
    URL.createObjectURL = (): string => 'blob:resume-preview';
    URL.revokeObjectURL = (): void => undefined;
    await TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { paramMap: new BehaviorSubject(convertToParamMap({ id: documentId })) },
        },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ResumeEditor);
    element = fixture.nativeElement as HTMLElement;
  });
  afterEach((): void => {
    fixture.destroy();
    http.verify();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('previews and saves edits', async (): Promise<void> => {
    await open();
    previewRequest().flush(preview());
    fixture.detectChanges();
    enter('#experience-0-bullet-0', 'Built Python APIs used by 40 clinics across Ontario');
    enter('#experience-0-title', 'Backend Intern');
    expect(element.textContent).toContain('Unsaved changes');
    expect(element.querySelector('.fit')?.textContent).toContain('catches up');
    await vi.advanceTimersByTimeAsync(1000);
    http.expectNone('/api/resumes/draft-preview');
    await vi.advanceTimersByTimeAsync(200);
    const request = previewRequest();
    expect(request.request.body).toMatchObject({
      experience: [{ title: 'Backend Intern' }],
      requirement_coverage: [{ entries: ['Backend Intern'] }],
    });
    expect(request.request.body).not.toHaveProperty('ai_usage');
    request.flush(preview(2, 3));
    fixture.detectChanges();
    expect(element.querySelector('.fit')?.textContent).toContain(
      'Runs about 3 lines past one page',
    );

    button('Save resume').click();
    const save = http.expectOne({ method: 'PUT', url: `/api/documents/${documentId}/resume` });
    expect(save.request.body).toMatchObject({
      revision: 0,
      resume: {
        experience: [{ bullets: ['Built Python APIs used by 40 clinics across Ontario'] }],
      },
    });
    const saved = {
      ...resume,
      requirement_coverage: [
        { requirement: 'Build Python APIs', importance: 'required', entries: ['Backend Intern'] },
      ],
      experience: [
        {
          ...resume.experience[0],
          title: 'Backend Intern',
          bullets: ['Built Python APIs used by 40 clinics across Ontario'],
        },
      ],
    };
    save.flush({
      ...attempt,
      resume: saved,
      generated_resume: resume,
      resume_edited_at: 300,
      resume_revision: 1,
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('Downloads and the application package now use');
    expect(element.textContent).toContain('Everything is saved');
    expect(button('Start from the generated version')).toBeDefined();
  });

  it('asks before leaving with unsaved edits', async (): Promise<void> => {
    await open();
    previewRequest().flush(preview());
    expect(fixture.componentInstance.canLeave()).toBe(true);
    enter('#resume-name', 'Alex B. Example');
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    expect(fixture.componentInstance.canLeave()).toBe(false);
    expect(confirm).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1200);
    previewRequest().flush(preview());
  });
});
