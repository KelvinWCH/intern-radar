import { parseExperienceContext } from './models/experience-context.models';
import { parsePreferences, parseResumeSettings } from './models/user-profile.models';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ResumeManager } from './resume-manager';

const resume = {
  about: null,
  goals: null,
  stories: [],
  answers: [],
  preferences: parsePreferences(null),
  resume_settings: parseResumeSettings(null),
  name: 'Alex Example',
  email: null,
  phone: null,
  location: 'Toronto',
  linkedin: null,
  linkedin_label: null,
  github: null,
  links: ['https://linkedin.com/in/alex'],
  education: [
    {
      institution: 'Example University',
      degree: 'BSc',
      field_of_study: 'Computer Science',
      location: null,
      start_date: '2024',
      end_date: null,
      bullets: ['Department scholarship.'],
      coursework: [],
      available_coursework: [],
    },
  ],
  experience: [
    {
      company: 'Example Studio',
      title: 'Developer',
      location: null,
      start_date: '2025',
      end_date: null,
      bullets: ['Built an API.'],
      context: parseExperienceContext(null),
      bullet_context: [null],
      raw_description: 'Private factual context.',
    },
  ],
  projects: [
    {
      name: 'Search tool',
      url: null,
      technologies: ['Python'],
      available_technologies: ['Python'],
      start_date: null,
      end_date: null,
      bullets: ['Built a search tool.'],
      context: parseExperienceContext(null),
      bullet_context: [null],
      raw_description: 'Project architecture and benchmark notes.',
    },
  ],
  skills: [
    {
      category: 'Languages',
      items: ['Python', 'TypeScript'],
      available_items: ['Python', 'TypeScript', 'Rust'],
    },
  ],
  additional_sections: [],
};

describe('ResumeManager', (): void => {
  let fixture: ComponentFixture<ResumeManager>;
  let element: HTMLElement;
  let http: HttpTestingController;
  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [ResumeManager],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ResumeManager);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    http.expectOne('/api/profile').flush({ profile: resume, revision: 3, updated_at: 1792238400 });
    await fixture.whenStable();
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

  async function editText(selector: string, value: string): Promise<void> {
    const input = element.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    if (!input) {
      throw new Error(`Missing input: ${selector}`);
    }
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }

  async function clickButton(label: string): Promise<void> {
    const button = element.querySelector<HTMLButtonElement>(`button[title="${label}"]`);
    if (!button) {
      throw new Error(`Missing button: ${label}`);
    }
    button.click();
    await fixture.whenStable();
  }

  async function editName(): Promise<void> {
    const name = element.querySelector<HTMLInputElement>('#resume-name');
    if (!name) {
      throw new Error('Missing name input');
    }
    name.value = 'Alex Updated';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
    element.querySelector<HTMLButtonElement>('button[type=submit]')?.click();
  }

  it('cleans phone and email', async (): Promise<void> => {
    await editText('#resume-phone', '6475550123');
    await editText('#resume-email', 'alex@example.com');
    await editName();
    const save = http.expectOne('/api/profile');
    expect(save.request.body).toEqual({
      revision: 3,
      profile: {
        ...resume,
        name: 'Alex Updated',
        phone: '+1 (647) 555-0123',
        email: 'alex@example.com',
      },
    });
    save.flush({ profile: resume, revision: 4, updated_at: 1792238401 });
    await fixture.whenStable();
  });

  it('keeps input after a conflict', async (): Promise<void> => {
    await editName();
    http
      .expectOne('/api/profile')
      .flush(
        { detail: 'Resume changed. Reload before saving.' },
        { status: 409, statusText: 'Conflict' },
      );
    await fixture.whenStable();
    expect(element.querySelector<HTMLInputElement>('#resume-name')?.value).toBe('Alex Updated');
    expect(element.textContent).toContain('Resume changed. Reload before saving.');
  });

  it.each([
    ['education', 'Education', 'institution'],
    ['experience', 'Experience', 'company'],
    ['projects', 'Projects', 'name'],
  ] as const)(
    'edits %s bullets as separate array items and preserves embedded line breaks',
    async (key, title, heading): Promise<void> => {
      const add = async (): Promise<void> => {
        element
          .querySelector(`#${key}-0-${heading}`)
          ?.closest('.entry')
          ?.querySelector<HTMLButtonElement>('.add-bullet')
          ?.click();
        await fixture.whenStable();
      };
      await add();
      await editText(`#${key}-0-bullet-1`, ' First line\nContinuation of the same bullet. ');
      await add();
      await editText(`#${key}-0-bullet-2`, 'Remove this middle bullet.');
      await add();
      await editText(`#${key}-0-bullet-3`, ' Final bullet. ');
      await clickButton(`Remove ${title} entry 1, bullet 3`);
      await clickButton(`Remove ${title} entry 1, bullet 1`);
      await add();
      await editText(`#${key}-0-bullet-2`, '   ');

      http.expectNone('/api/profile');
      expect(element.querySelector<HTMLTextAreaElement>(`#${key}-0-bullet-0`)?.value).toBe(
        ' First line\nContinuation of the same bullet. ',
      );
      expect(element.querySelector<HTMLTextAreaElement>(`#${key}-0-bullet-1`)?.value).toBe(
        ' Final bullet. ',
      );

      const saved = {
        ...resume,
        [key]: resume[key].map((entry) => ({
          ...entry,
          bullets: ['First line\nContinuation of the same bullet.', 'Final bullet.'],
          ...(key === 'education' ? {} : { bullet_context: [null, null] }),
        })),
      };
      element.querySelector<HTMLButtonElement>('button[type=submit]')?.click();
      const request = http.expectOne('/api/profile');
      expect(request.request.body).toEqual({ revision: 3, profile: saved });
      await fixture.whenStable();
      expect(element.querySelector<HTMLFieldSetElement>('fieldset')?.disabled).toBe(true);
      request.flush({ profile: saved, revision: 4, updated_at: 1792238401 });
      await fixture.whenStable();
      expect(element.querySelectorAll(`[id^="${key}-0-bullet-"]`)).toHaveLength(2);
    },
  );
  async function clickText(text: string): Promise<void> {
    const button = [...element.querySelectorAll<HTMLButtonElement>('button')].find(
      (candidate): boolean => candidate.textContent.trim() === text,
    );
    if (!button) {
      throw new Error(`Missing button: ${text}`);
    }
    button.click();
    await fixture.whenStable();
  }

  function submit(): void {
    element.querySelector<HTMLButtonElement>('button[type=submit]')?.click();
  }

  it('edits the profile as json', async (): Promise<void> => {
    await editName();
    http.expectOne('/api/profile').flush({ detail: 'Busy' }, { status: 503, statusText: '' });
    await fixture.whenStable();
    await clickText('JSON');
    const json = element.querySelector<HTMLTextAreaElement>('#resume-json');
    expect(JSON.parse(json?.value ?? '')).toEqual({ ...resume, name: 'Alex Updated' });
    expect(element.querySelector('#resume-name')).toBeNull();

    const pasted = {
      ...resume,
      name: 'Alex Pasted',
      skills: [{ category: 'Languages', items: ['Go'] }],
    };
    await editText('#resume-json', JSON.stringify(pasted));
    submit();
    const request = http.expectOne('/api/profile');
    expect(request.request.body).toEqual({
      revision: 3,
      profile: {
        ...pasted,
        skills: [{ category: 'Languages', items: ['Go'], available_items: ['Go'] }],
      },
    });
    request.flush({ profile: pasted, revision: 4, updated_at: 1792238401 });
    await fixture.whenStable();
    expect(
      JSON.parse(element.querySelector<HTMLTextAreaElement>('#resume-json')?.value ?? ''),
    ).toEqual({
      ...pasted,
      skills: [{ category: 'Languages', items: ['Go'], available_items: ['Go'] }],
    });

    await clickText('Form');
    expect(element.querySelector<HTMLInputElement>('#resume-name')?.value).toBe('Alex Pasted');
    const skillPicker = element
      .querySelector('#skills-0-category')
      ?.closest('.entry')
      ?.querySelector('app-inventory-selector');
    expect(skillPicker?.querySelector('.stack-chip.chosen')?.textContent).toContain('Go');
  });

  it('keeps invalid json', async (): Promise<void> => {
    await clickText('JSON');
    await editText('#resume-json', '{"name": ');
    submit();
    await fixture.whenStable();
    http.expectNone('/api/profile');
    expect(element.textContent).toContain('The JSON is not valid');
    await editText('#resume-json', JSON.stringify({ ...resume, links: 'not a list' }));
    await clickText('Form');
    expect(element.textContent).toContain('does not match the resume format');
    expect(element.querySelector<HTMLTextAreaElement>('#resume-json')?.value).toContain(
      'not a list',
    );
  });
});

describe('ResumeManager loading', (): void => {
  let fixture: ComponentFixture<ResumeManager>;
  let element: HTMLElement;
  let http: HttpTestingController;

  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [ResumeManager],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ResumeManager);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
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

  it('retries after a load failure', async (): Promise<void> => {
    http.expectOne('/api/profile').flush({}, { status: 503, statusText: 'Unavailable' });
    await fixture.whenStable();
    expect(element.querySelector('.profile-loading')).toBeNull();
    expect(element.querySelector('.notice.error')).not.toBeNull();
    element.querySelector<HTMLButtonElement>('button')?.click();
    await fixture.whenStable();
    expect(element.querySelector('.profile-loading')).not.toBeNull();
    expect(element.querySelector('.notice.error')).toBeNull();
    http.expectOne('/api/profile').flush({ profile: null, revision: 0, updated_at: null });
    await fixture.whenStable();
    expect(element.querySelector('.profile-loading')).toBeNull();
    expect(element.querySelector<HTMLInputElement>('#resume-name')?.value).toBe('');
    expect(element.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
  });
});
