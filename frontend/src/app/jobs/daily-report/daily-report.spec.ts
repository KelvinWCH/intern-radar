import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import type { Observable } from 'rxjs';
import { Subject, map, of } from 'rxjs';
import type { ScrapeSummary } from '../../scrapes/models/scrape-summary.models';
import { moveDay, startOfDay } from '../job-day';
import { JobsService } from '../jobs.service';
import type { JobPage, JobSummary } from '../models/job.models';
import { DailyReport } from './daily-report';

const job: JobSummary = {
  user: {
    status: 'new',
    notes: '',
    applied_at: null,
    follow_up_at: null,
    updated_at: null,
    version: 0,
    documents: [],
  },
  id: '1',
  sourceType: 'scraped',
  rawDescription: 'Build useful tools with a small team.',
  company: 'Example Company',
  title: 'Software Engineering Intern',
  locations: ['Toronto, ON'],
  terms: ['Summer 2027'],
  category: 'Software Engineering',
  summary: 'Build useful tools with a small team.',
  applicationUrl: 'https://example.com/jobs/1',
  applyUrl: 'https://example.com/apply/1',
  firstSeenAt: Math.floor(new Date().getTime() / 1000),
};

describe('DailyReport', (): void => {
  let fixture: ComponentFixture<DailyReport>;
  let element: HTMLElement;
  let requests: {
    day: Date;
    offset: number;
    response: Subject<readonly JobSummary[]>;
  }[];

  function latest(): Subject<readonly JobSummary[]> {
    const request = requests.at(-1);
    if (!request) {
      throw new Error('Expected a daily jobs request.');
    }
    return request.response;
  }

  function button(label: string): HTMLButtonElement {
    const result = Array.from(element.querySelectorAll('button')).find(
      (candidate): boolean =>
        candidate.getAttribute('title') === label || candidate.textContent.trim() === label,
    );
    if (!result) {
      throw new Error(`Missing button: ${label}`);
    }
    return result;
  }

  beforeEach(async (): Promise<void> => {
    localStorage.clear();
    requests = [];
    await TestBed.configureTestingModule({
      imports: [DailyReport],
      providers: [
        provideRouter([]),
        {
          provide: JobsService,
          useValue: {
            scrapeSummaryForDay: (): Observable<ScrapeSummary> =>
              of({
                created: 8,
                duplicates: 12,
                updated: 3,
                runs: 4,
                failedRuns: 1,
                runningRuns: 0,
                inputTokens: 1500,
                outputTokens: 500,
                scrapeSeconds: 125,
              }),
            forDay: (day: Date, offset = 0): Observable<JobPage> => {
              const response = new Subject<readonly JobSummary[]>();
              requests.push({ day, offset, response });
              return response.pipe(
                map((items): JobPage => ({
                  items,
                  total: items.length + offset,
                  limit: 100,
                  offset,
                })),
              );
            },
          },
        },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DailyReport);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    await fixture.whenStable();
  });

  it('shows todays jobs', async (): Promise<void> => {
    expect(requests[0]?.day).toEqual(startOfDay(new Date()));
    expect(element.textContent).toContain('Loading jobs');
    const pagination = element.querySelector('.pagination');
    const usage = element.querySelector('.usage-row');
    expect(element.querySelectorAll('.skeleton-row')).toHaveLength(6);
    expect(pagination).not.toBeNull();
    expect(usage).not.toBeNull();
    expect(button('Next day').disabled).toBe(true);
    latest().next([job]);
    await fixture.whenStable();
    expect(element.textContent).toContain('1 open listing');
    expect(element.querySelectorAll('.skeleton-row')).toHaveLength(0);
    expect(element.querySelector('.pagination')).toBe(pagination);
    expect(element.querySelector('.usage-row')).toBe(usage);
    expect(element.textContent).toContain(job.title);
    expect(element.textContent).toContain('Toronto, ON');
    expect(element.querySelector('h3 a')?.getAttribute('href')).toBe(job.applicationUrl);
    expect(element.querySelector('.job-link')?.getAttribute('href')).toBe(job.applyUrl);
    expect(element.querySelector('app-daily-statistics')?.textContent).toContain('Duplicates');
    expect(element.querySelectorAll('dd')[0]?.textContent.trim()).toBe('8');
    expect(element.querySelectorAll('dd')[1]?.textContent.trim()).toBe('12');
  });

  it('moves between days', async (): Promise<void> => {
    const today = startOfDay(new Date());
    button('Previous day').click();
    await fixture.whenStable();
    expect(requests.at(-1)?.day).toEqual(moveDay(today, -1));
    expect(button('Next day').disabled).toBe(false);
    button('Next day').click();
    await fixture.whenStable();
    expect(requests.at(-1)?.day).toEqual(today);
    expect(button('Next day').disabled).toBe(true);
    button('Previous day').click();
    await fixture.whenStable();
    button('Previous day').click();
    await fixture.whenStable();
    button('Today').click();
    await fixture.whenStable();
    expect(requests.at(-1)?.day).toEqual(today);
  });

  it('retries after an error', async (): Promise<void> => {
    latest().error(new Error('Offline'));
    await fixture.whenStable();
    expect(element.querySelector('.message-panel')?.textContent).toContain("couldn't load");
    button('Try again').click();
    await fixture.whenStable();
    expect(requests).toHaveLength(2);
    expect(requests[1]?.day).toEqual(requests[0]?.day);
    latest().next([{ ...job, applyUrl: null }]);
    await fixture.whenStable();
    expect(element.querySelector('.job-link')?.getAttribute('href')).toBe(job.applicationUrl);
  });
});
