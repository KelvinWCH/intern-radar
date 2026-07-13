import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import type { Observable } from 'rxjs';
import { of, throwError } from 'rxjs';
import { moveDay } from '../job-day';
import { JobsService } from '../jobs.service';
import type { JobOverview, JobQuery } from '../models/job-query.models';
import type { JobPage, JobSummary } from '../models/job.models';
import { JobLibrary } from './job-library';
import type { JobUserData, JobUserEdit } from '../models/user-data.models';

const job: JobSummary = {
  id: '1',
  company: 'Wealthsimple',
  title: 'Software Engineering Intern',
  locations: ['Toronto, ON'],
  terms: ['Summer 2027'],
  category: null,
  summary: null,
  sourceType: 'scraped',
  applicationUrl: null,
  applyUrl: null,
  rawDescription: null,
  firstSeenAt: 1792200000,
  prestige: true,
  user: {
    status: 'interviewing',
    notes: '',
    applied_at: null,
    follow_up_at: 1792500000,
    updated_at: null,
    version: 0,
    documents: [],
  },
};

describe('JobLibrary', (): void => {
  it('deletes, undoes and changes range', async (): Promise<void> => {
    const weeks: Date[] = [];
    let removed = false;
    const currentJob = { ...job, firstSeenAt: moveDay(new Date(), -2).getTime() / 1000 };
    await TestBed.configureTestingModule({
      imports: [JobLibrary],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: {} } } },
        {
          provide: JobsService,
          useValue: {
            forCalendar: (_query: JobQuery, week: Date): Observable<JobPage> => {
              weeks.push(week);
              return of({
                items: removed ? [] : [currentJob],
                total: removed ? 0 : 1,
                offset: 0,
                limit: 100,
              });
            },
            overview: (): Observable<JobOverview> =>
              of({ total: removed ? 0 : 1, statuses: {}, sources: [] }),
            delete: (): Observable<JobSummary> => {
              removed = true;
              return of({ ...currentJob, deletedAt: Date.now() / 1000 });
            },
            restore: (): Observable<JobSummary> => {
              removed = false;
              return of({ ...currentJob, deletedAt: null });
            },
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(JobLibrary);
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(element.querySelectorAll('.day-column')).toHaveLength(3);
    element.querySelector<HTMLButtonElement>('.delete-job')?.click();
    await fixture.whenStable();
    expect(element.querySelectorAll('.calendar-card')).toHaveLength(0);
    const undo = Array.from(element.querySelectorAll('button')).find(
      (button): boolean => button.textContent.trim() === 'Undo',
    );
    expect(undo).toBeDefined();
    undo?.click();
    await fixture.whenStable();
    expect(element.querySelectorAll('.calendar-card')).toHaveLength(1);
    element.querySelector<HTMLButtonElement>('[title="Previous 3 days"]')?.click();
    await fixture.whenStable();
    const previous = moveDay(new Date(), -5);
    expect(weeks.at(-1)).toEqual(previous);
    expect(element.querySelectorAll('.calendar-card')).toHaveLength(0);
  });
  it('applies filters and sorting', async (): Promise<void> => {
    const requests: { query: JobQuery; offset: number }[] = [];
    await TestBed.configureTestingModule({
      imports: [JobLibrary],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { tracker: true } } } },
        {
          provide: JobsService,
          useValue: {
            browse: (query: JobQuery, offset = 0): Observable<JobPage> => {
              requests.push({ query: { ...query }, offset });
              return of({ items: [{ ...job, copies: 3 }], total: 1, offset, limit: 30 });
            },
            overview: (): Observable<JobOverview> =>
              of({ total: 2, statuses: { new: 1, interviewing: 1 }, sources: [] }),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(JobLibrary);
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(requests[0]?.query.sort).toBe('match');
    expect(requests[0]?.query.tracked).toBe(true);
    expect(requests[0]?.query.scope).toBe('all');
    expect(element.querySelector('.scraped-scope button')).toBeNull();
    expect(element.querySelector<HTMLElement>('#advanced-filters')?.hidden).toBe(true);
    expect(element.querySelector('.job-card')?.getAttribute('data-status')).toBe('interviewing');
    expect(element.textContent).toContain('Known name');
    expect(element.querySelector('.copies-badge')?.textContent).toContain('3 boards');
    expect(element.textContent).toContain('Follow up');
    expect(element.textContent).toContain('Posted date unknown');
    const sort = element.querySelector<HTMLSelectElement>('#sort-jobs');
    if (!sort) {
      throw new Error('Missing sort control');
    }
    sort.value = 'company';
    sort.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(requests.at(-1)?.query.sort).toBe('company');
    expect(requests.at(-1)?.offset).toBe(0);
    sort.value = 'posted';
    sort.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(requests.at(-1)?.query.sort).toBe('posted');
    const match = element.querySelector<HTMLSelectElement>('#filter-match');
    if (!match) {
      throw new Error('Missing match filter');
    }
    match.value = '85';
    match.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(requests.at(-1)?.query.match).toBe('85');
    expect(requests.at(-1)?.offset).toBe(0);
    const toronto = element.querySelector<HTMLButtonElement>('.toronto-switch');
    if (!toronto) {
      throw new Error('Missing Toronto switch');
    }
    expect(toronto.classList.contains('checked')).toBe(false);
    toronto.click();
    await fixture.whenStable();
    expect(toronto.classList.contains('checked')).toBe(true);
    expect(requests.at(-1)?.query.toronto).toBe(true);
    expect(requests.at(-1)?.query.match).toBe('85');
    element.querySelector<HTMLButtonElement>('.filter-toggle')?.click();
    await fixture.whenStable();
    expect(element.querySelector<HTMLElement>('#advanced-filters')?.hidden).toBe(false);
    const source = element.querySelector<HTMLSelectElement>('#filter-activity');
    if (!source) {
      throw new Error('Missing listing status filter');
    }
    source.value = 'closed';
    source.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(requests.at(-1)?.query.activity).toBe('closed');
    element.querySelector<HTMLButtonElement>('[data-status="interviewing"]')?.click();
    await fixture.whenStable();
    expect(requests.at(-1)?.query.application_status).toBe('interviewing');
    element.querySelector<HTMLButtonElement>('[data-status="interviewing"]')?.click();
    await fixture.whenStable();
    expect(requests.at(-1)?.query.application_status).toBe('');
  });

  it('handles load errors', async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [JobLibrary],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { tracker: true } } } },
        {
          provide: JobsService,
          useValue: {
            browse: (): Observable<never> => throwError(() => new Error('offline')),
            overview: (): Observable<never> => throwError(() => new Error('offline')),
          },
        },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(JobLibrary);
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.async-status')?.textContent).toContain('Retry');
    expect(element.querySelectorAll('.stage-tab').length).toBe(7);
  });
});

describe('Application status edits', (): void => {
  const savedJob: JobSummary = {
    ...job,
    user: { ...job.user, status: 'saved', notes: 'Keep my interview notes', version: 7 },
  };

  async function setup(
    browse: (query: JobQuery, offset?: number) => Observable<JobPage>,
    updateUser: (id: string, edit: JobUserEdit) => Observable<JobUserData>,
    overview = vi.fn((): Observable<JobOverview> =>
      of({ total: 1, statuses: { saved: 1 }, sources: [] }),
    ),
  ): Promise<ComponentFixture<JobLibrary>> {
    await TestBed.configureTestingModule({
      imports: [JobLibrary],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { tracker: true } } } },
        { provide: JobsService, useValue: { browse, overview, updateUser } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(JobLibrary);
    await fixture.whenStable();
    return fixture;
  }

  it('unsaves a job', async (): Promise<void> => {
    const browse = vi.fn((): Observable<JobPage> =>
      of({ items: [savedJob], total: 1, offset: 0, limit: 30 }),
    );
    const overview = vi.fn((): Observable<JobOverview> =>
      of({ total: 1, statuses: { saved: 1 }, sources: [] }),
    );
    const update = vi.fn((_id: string, edit: JobUserEdit): Observable<JobUserData> =>
      of({ ...savedJob.user, ...edit, version: 8 }),
    );
    const fixture = await setup(browse, update, overview);
    const element = fixture.nativeElement as HTMLElement;
    element.querySelector<HTMLButtonElement>('.undo-status')?.click();
    await fixture.whenStable();
    expect(update).toHaveBeenCalledExactlyOnceWith(savedJob.id, {
      status: 'new',
      notes: savedJob.user.notes,
      applied_at: null,
      follow_up_at: savedJob.user.follow_up_at,
      version: 7,
    });
    expect(element.querySelector('.job-card')).toBeNull();
    expect(element.textContent).toContain('The job is still in Jobs');
    expect(browse).toHaveBeenCalledOnce();
    expect(overview).toHaveBeenCalledTimes(2);
  });
});
