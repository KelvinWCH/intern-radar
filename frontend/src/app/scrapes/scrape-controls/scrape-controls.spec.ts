import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ScrapeStatusStore } from '../scrape-status.store';
import { ScrapeControls } from './scrape-controls';

const source = {
  id: 'github:simplify-summer2027',
  name: 'Summer jobs',
  group: 'github',
  enabled: true,
  source_name: 'sample',
  reason: null,
};
const settings = {
  request_id: '11111111-1111-4111-8111-111111111111',
  sources: [source.id],
  max_runtime_seconds: 1800,
  max_ai_calls: 100,
  max_downloads: 100,
  max_age_days: 2,
};
const task = {
  id: settings.request_id,
  settings,
  status: 'running',
  created_at: 1792238400,
  started_at: 1792238400,
  finished_at: null,
  elapsed_seconds: 10,
  cancel_requested: false,
  error: null,
  runs: [],
  events: [
    {
      id: '1',
      run_id: '7',
      created_at: 1792238401,
      level: 'info',
      message: 'Launching headless Chrome',
    },
    {
      id: '2',
      run_id: '7',
      created_at: 1792238402,
      level: 'error',
      message: 'Extraction failed for https://example.com/big: too large',
    },
  ],
  usage: { input_tokens: 12000, output_tokens: 400 },
  progress: {
    sources_total: 1,
    sources_finished: 0,
    current_source: 'simplify',
    phase: 'reading and extracting',
    items_done: 3,
    items_total: 4,
    percent: 75,
  },
};

describe('ScrapeControls', (): void => {
  let fixture: ComponentFixture<ScrapeControls>;
  let element: HTMLElement;
  let http: HttpTestingController;
  beforeEach(async (): Promise<void> => {
    await TestBed.configureTestingModule({
      imports: [ScrapeControls],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ScrapeControls);
    element = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
    http.expectOne('/api/scrapes/activity').flush({ busy: false, runs: [], events: [] });
    http.expectOne('/api/scrapes/sources').flush([
      source,
      {
        ...source,
        id: 'github:disabled',
        name: 'Unavailable source',
        enabled: false,
        reason: 'No adapter',
      },
      { ...source, id: 'company:example', name: 'Example company', group: 'company' },
    ]);
  });
  afterEach((): void => {
    fixture.destroy();
    http.verify();
  });

  function button(label: string): HTMLButtonElement {
    const result = Array.from(element.querySelectorAll('button')).find(
      (item): boolean => item.textContent.trim() === label,
    );
    if (!result) {
      throw new Error(`Missing button ${label}`);
    }
    return result;
  }

  it('sends selected sources', async (): Promise<void> => {
    http.expectOne('/api/scrapes').flush([]);
    await fixture.whenStable();
    button('Select visible').click();
    expect(element.querySelectorAll<HTMLInputElement>('input[type=checkbox]')[1]?.disabled).toBe(
      true,
    );
    button('Run scrape · no AI').click();
    const request = http.expectOne('/api/scrapes');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toMatchObject({
      sources: [source.id],
      max_runtime_seconds: 1800,
      use_ai: false,
      max_ai_calls: 20,
      max_downloads: 100,
      max_age_days: 2,
    });
    request.flush({ ...task, status: 'completed', finished_at: 1792238410 });
    await fixture.whenStable();
    expect(element.textContent).toContain('Completed');
  });

  it('reconnects and cancels', async (): Promise<void> => {
    http.expectOne('/api/scrapes').flush([task]);
    await fixture.whenStable();
    expect(button('Run scrape · no AI').disabled).toBe(true);
    expect(element.textContent).toContain('Reading postings');
    expect(element.textContent).toContain('75%');
    expect(element.textContent).toContain('3 / 4 postings');
    expect(element.textContent).toContain('12k');
    expect(element.querySelector('.console-line')).toBeNull();
    expect(TestBed.inject(ScrapeStatusStore).task()?.events).toHaveLength(2);
    button('Cancel remaining work').click();
    const cancel = http.expectOne(`/api/scrapes/${task.id}/cancel`);
    expect(cancel.request.method).toBe('POST');
    cancel.flush({ ...task, cancel_requested: true });
    await fixture.whenStable();
    expect(element.textContent).toContain('Stopping…');
    expect(button('Cancel remaining work').disabled).toBe(true);
    fixture.destroy();
    http.expectNone(
      (request): boolean => request.method === 'POST' && request.url === '/api/scrapes',
    );
  });

  it('only uses ai when checked', async (): Promise<void> => {
    http.expectOne('/api/scrapes').flush([]);
    await fixture.whenStable();
    const checkbox = element.querySelector<HTMLInputElement>('#scrape-use-ai');
    if (!checkbox) {
      throw new Error('Missing AI opt-in');
    }
    expect(checkbox.checked).toBe(false);
    checkbox.click();
    await fixture.whenStable();
    expect(element.querySelector('#scrape-calls')).not.toBeNull();
    button('Run with AI enrichment').click();
    const request = http.expectOne('/api/scrapes');
    expect(request.request.body).toMatchObject({ use_ai: true, max_ai_calls: 20 });
    request.flush({ ...task, status: 'completed', finished_at: 1792238410 });
    await fixture.whenStable();
    expect(checkbox.checked).toBe(false);
    expect(element.querySelector('#scrape-calls')).toBeNull();
  });
});
