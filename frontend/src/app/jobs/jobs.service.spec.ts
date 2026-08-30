import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { JobsService } from './jobs.service';

const apiJob = {
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
  source_type: 'scraped',
  raw_description: 'Build useful tools with a small team.',
  company: 'Example Company',
  title: 'Software Engineering Intern',
  locations: ['Toronto, ON'],
  terms: ['Summer 2027'],
  category: null,
  summary: null,
  application_url: 'https://example.com/jobs/1',
  apply_url: null,
  first_seen_at: 1792238400,
};

describe('JobsService', (): void => {
  let service: JobsService;
  let http: HttpTestingController;

  beforeEach((): void => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(JobsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach((): void => {
    http.verify();
  });

  it('loads lists and details', async (): Promise<void> => {
    const pageResult = firstValueFrom(service.forDay(new Date(2026, 9, 17)));
    const list = http.expectOne((req): boolean => req.url === '/api/jobs');
    const { raw_description: description, ...compact } = apiJob;
    list.flush({ items: [compact], total: 1, limit: 100, offset: 0 });
    const page = await pageResult;
    expect(page.items[0]?.rawDescription).toBeNull();
    expect(page.items[0]?.company).toBe(apiJob.company);

    const detailResult = firstValueFrom(service.get(apiJob.id));
    const detail = http.expectOne('/api/jobs/1');
    detail.flush({ ...apiJob, raw_payload: { original: 'retained' } });
    expect((await detailResult).rawDescription).toBe(description);
  });

  it('deletes and restores jobs', async (): Promise<void> => {
    const deleted = firstValueFrom(service.delete('1'));
    const request = http.expectOne('/api/jobs/1');
    expect(request.request.method).toBe('DELETE');
    request.flush({ ...apiJob, deleted_at: 1792238400, company_tier: 'tech' });
    expect((await deleted).deletedAt).toBe(1792238400);
    const restored = firstValueFrom(service.restore('1'));
    http.expectOne('/api/jobs/1/restore').flush({ ...apiJob, deleted_at: null });
    expect((await restored).deletedAt).toBeNull();
  });

  it.each([
    { ...apiJob, application_url: 'javascript:alert(1)' },
    { ...apiJob, id: 1 },
    { ...apiJob, date_posted: 'yesterday' },
  ])('rejects malformed job data before rendering it', async (invalidJob): Promise<void> => {
    const result = firstValueFrom(service.forDay(new Date()));
    http
      .expectOne((req): boolean => req.url === '/api/jobs')
      .flush({
        items: [invalidJob],
        total: 1,
        limit: 100,
        offset: 0,
      });
    await expect(result).rejects.toThrow();
  });

  it('fails on a truncated page', async (): Promise<void> => {
    const result = firstValueFrom(service.forDay(new Date()));
    http
      .expectOne((req): boolean => req.url === '/api/jobs')
      .flush({
        items: [],
        total: 1,
        limit: 100,
        offset: 0,
      });
    await expect(result).rejects.toThrow('Inconsistent jobs page.');
  });
});
