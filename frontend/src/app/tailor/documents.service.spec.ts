import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DocumentsService } from './documents.service';
import type { DocumentDetail } from './models/document.models';

const pending = {
  id: '00000000-0000-4000-8000-000000000001',
  job_id: 'listing-7f5a1b937287e2b3433ad9cbd68a92f3',
  company: 'Example',
  title: 'Engineer',
  status: 'running',
  created_at: 100,
  finished_at: null,
  has_resume: false,
  has_cover_letter: false,
  error: null,
  profile_revision: 1,
  job_description: 'Build APIs',
  resume: null,
  cover_letter: null,
  events: [{ id: 1, created_at: 100, stage: 'queued', message: 'Accepted' }],
};

describe('Background tailoring', (): void => {
  let service: DocumentsService;
  let http: HttpTestingController;

  beforeEach((): void => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(DocumentsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach((): void => {
    http.verify();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('polls until done', (): void => {
    const snapshots: DocumentDetail[] = [];
    let completed = false;
    service
      .tailor('listing-7f5a1b937287e2b3433ad9cbd68a92f3', {
        request_id: pending.id,
        include_resume: true,
        include_cover_letter: false,
      })
      .subscribe({
        next: (value): void => {
          snapshots.push(value);
        },
        complete: (): void => {
          completed = true;
        },
      });
    http
      .expectOne('/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks')
      .flush(pending);
    expect(snapshots[0]?.status).toBe('running');
    vi.advanceTimersByTime(1000);
    const poll = http.expectOne(`/api/documents/${pending.id}`);
    vi.advanceTimersByTime(5000);
    http.expectNone(`/api/documents/${pending.id}`);
    poll.flush({
      ...pending,
      events: [
        ...pending.events,
        { id: 2, created_at: 102, stage: 'ai', message: 'Generating resume' },
      ],
    });
    expect(snapshots[1]?.events?.[1]?.stage).toBe('ai');
    vi.advanceTimersByTime(1000);
    http
      .expectOne(`/api/documents/${pending.id}`)
      .flush({ ...pending, status: 'completed', finished_at: 110 });
    expect(completed).toBe(true);
    vi.advanceTimersByTime(10000);
    http.expectNone(`/api/documents/${pending.id}`);
  });

  it('stops polling for review', (): void => {
    const snapshots: DocumentDetail[] = [];
    service.watch(pending.id).subscribe((value): void => {
      snapshots.push(value);
    });
    http.expectOne(`/api/documents/${pending.id}`).flush(pending);
    vi.advanceTimersByTime(1000);
    http.expectOne(`/api/documents/${pending.id}`).flush({ ...pending, status: 'awaiting_review' });
    vi.advanceTimersByTime(10000);
    http.expectNone(`/api/documents/${pending.id}`);
    expect(snapshots.at(-1)?.status).toBe('awaiting_review');
    service.reviewResearch(pending.id, { action: 'continue', revision: 1 }).subscribe();
    const review = http.expectOne(`/api/documents/${pending.id}/research-review`);
    expect(review.request.method).toBe('POST');
    expect(review.request.body).toEqual({ action: 'continue', revision: 1 });
    review.flush(pending);
  });

  it('retries outages', (): void => {
    const snapshots: DocumentDetail[] = [];
    service.watch(pending.id).subscribe((value): void => {
      snapshots.push(value);
    });
    http
      .expectOne(`/api/documents/${pending.id}`)
      .flush({}, { status: 503, statusText: 'Unavailable' });
    vi.advanceTimersByTime(1500);
    http.expectOne(`/api/documents/${pending.id}`).flush(pending);
    vi.advanceTimersByTime(1000);
    http
      .expectOne(`/api/documents/${pending.id}`)
      .flush({ ...pending, status: 'failed', error: 'Generation failed' });
    expect(snapshots.at(-1)?.status).toBe('failed');
    vi.advanceTimersByTime(5000);
    http.expectNone(`/api/documents/${pending.id}`);
    http.expectNone('/api/jobs/listing-7f5a1b937287e2b3433ad9cbd68a92f3/tailor-tasks');
  });
});
