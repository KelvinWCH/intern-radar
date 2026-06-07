import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { TailoringFlow } from './tailoring-flow';
import type { DocumentDetail } from '../models/document.models';
const savedDocument: DocumentDetail = {
  id: 'example-document',
  job_id: 'example-job',
  company: 'Example',
  title: 'Engineer',
  status: 'running',
  created_at: 100,
  finished_at: null,
  has_resume: true,
  has_cover_letter: true,
  error: null,
  profile_revision: 1,
  job_description: 'Build tools.',
  resume: null,
  cover_letter: null,
  stages: [
    { key: 'research', label: 'Research', model: 'model', status: 'completed', message: 'Saved' },
    { key: 'resume', label: 'Resume', model: 'model', status: 'running', message: 'Writing' },
    {
      key: 'cover_letter',
      label: 'Cover letter',
      model: 'model',
      status: 'completed',
      message: 'Saved',
    },
    { key: 'reviewer', label: 'Review', model: 'model', status: 'running', message: 'Reviewing' },
  ],
};

describe('TailoringFlow', (): void => {
  let fixture: ComponentFixture<TailoringFlow>;
  let element: HTMLElement;
  let restoreBounds: () => void;

  beforeEach(async (): Promise<void> => {
    vi.clearAllMocks();
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
    const bounds = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function (this: HTMLElement): DOMRect {
        if (this.classList.contains('flow-canvas')) {
          return new DOMRect(0, 0, 1200, 400);
        }
        const positions: Record<string, [number, number]> = {
          source: [0, 42],
          company: [0, 204],
          research: [200, 42],
          profile: [200, 204],
          resume: [400, 42],
          cover_letter: [400, 204],
          pdf_diagnostics: [600, 123],
          reviewer: [800, 123],
          saved: [1000, 123],
        };
        const point = positions[this.dataset['node'] ?? ''];
        return point ? new DOMRect(point[0], point[1], 170, 150) : new DOMRect();
      });
    restoreBounds = (): void => {
      bounds.mockRestore();
    };
    await TestBed.configureTestingModule({ imports: [TailoringFlow] }).compileComponents();
    fixture = TestBed.createComponent(TailoringFlow);
    element = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
    await vi.dynamicImportSettled();
    await fixture.whenStable();
  });

  afterEach((): void => {
    fixture.destroy();
    restoreBounds();
    vi.unstubAllGlobals();
  });

  it('shows parallel writers', async (): Promise<void> => {
    fixture.componentRef.setInput('document', {
      ...savedDocument,
      stages: savedDocument.stages?.map((stage) => ({
        ...stage,
        status: ['resume', 'cover_letter'].includes(stage.key) ? 'running' : 'completed',
      })),
    });
    await fixture.whenStable();
    const current = element.querySelector('.flow-current');
    expect(current?.textContent).toContain('In progress');
    expect(current?.textContent.replace(/\s+/g, ' ')).toContain('Resume, Cover letter');
    expect(element.querySelectorAll('.current')).toHaveLength(2);
    fixture.componentRef.setInput('document', {
      ...savedDocument,
      stages: savedDocument.stages?.map((stage) => ({
        ...stage,
        status: stage.key === 'reviewer' ? 'running' : 'completed',
      })),
    });
    await fixture.whenStable();
    expect(current?.textContent).toContain('Independent review');
    expect(element.querySelectorAll('.current')).toHaveLength(1);
    expect(element.querySelector('[data-node="reviewer"] .current')).not.toBeNull();
    expect(element.querySelector('[data-node="resume"] .current')).toBeNull();
  });

  it.each(['research', 'reviewer'])(
    'makes the %s review pause the prominent stage',
    async (key): Promise<void> => {
      fixture.componentRef.setInput('document', {
        ...savedDocument,
        status: 'awaiting_review',
        stages: savedDocument.stages?.map((stage) => ({
          ...stage,
          status: stage.key === key ? 'awaiting_review' : 'completed',
        })),
      });
      await fixture.whenStable();
      expect(element.querySelector('.current-stage')?.getAttribute('data-status')).toBe(
        'awaiting_review',
      );
      expect(element.querySelector('.current-stage strong')?.textContent).toBe('Needs your review');
      expect(element.querySelector(`[data-node="${key}"] .current`)).not.toBeNull();
      expect(
        element.querySelector(`[data-node="${key}"] .node-state .pi-exclamation-circle`),
      ).not.toBeNull();
    },
  );

  it('shows a failed stage first', async (): Promise<void> => {
    fixture.componentRef.setInput('document', {
      ...savedDocument,
      stages: savedDocument.stages?.map((stage) =>
        stage.key === 'cover_letter' ? { ...stage, status: 'failed' } : stage,
      ),
    });
    await fixture.whenStable();
    expect(element.querySelector('.current-stage strong')?.textContent).toBe('Failed');
    expect(element.querySelector('.current-stage span')?.textContent.trim()).toBe('Cover letter');
    expect(element.querySelectorAll('.current')).toHaveLength(1);
    expect(element.querySelector('[data-node="cover_letter"] .current')).not.toBeNull();
  });

  it('shows a one-shot call', async (): Promise<void> => {
    const oneShot: DocumentDetail = {
      ...savedDocument,
      mode: 'one_shot',
      one_shot_step: 'review',
      stages: [
        { key: 'research', label: 'Research', model: 'm', status: 'running', message: 'One call' },
        { key: 'resume', label: 'Resume', model: 'm', status: 'queued', message: 'Waiting' },
        { key: 'cover_letter', label: 'Letter', model: 'm', status: 'queued', message: 'Waiting' },
      ],
    };
    fixture.componentRef.setInput('document', oneShot);
    await fixture.whenStable();
    const cards = [...element.querySelectorAll<HTMLElement>('.node-slot')].map(
      (slot) => slot.dataset['node'],
    );
    expect(cards).toEqual([
      'source',
      'company',
      'profile',
      'one_shot',
      'resume',
      'cover_letter',
      'pdf_diagnostics',
      'saved',
    ]);
    expect(element.querySelector('[data-node="reviewer"]')).toBeNull();
    expect(element.querySelectorAll('.revision-route')).toHaveLength(0);
    expect(
      element.querySelector<HTMLElement>('.flow-grid')?.style.getPropertyValue('--flow-columns'),
    ).toBe('5');
    const into = [...element.querySelectorAll('.flow-wires g')].map((wire) =>
      wire.getAttribute('data-to'),
    );
    expect(into.filter((to) => to === 'one_shot')).toHaveLength(3);
    const steps = [...element.querySelectorAll('.call-steps li')].map((step) => [
      step.textContent.replace(/\s+/g, ' ').trim(),
      step.getAttribute('data-state'),
    ]);
    expect(steps).toEqual([
      ['Research', 'done'],
      ['Draft', 'done'],
      ['Self-review', 'current'],
      ['Revise', 'waiting'],
    ]);
    const call = element.querySelector('[data-node="one_shot"] .flow-node');
    expect(call?.classList.contains('current')).toBe(true);
    expect(element.querySelector('.current-stage')?.textContent).toContain('Reviewing its drafts');

    fixture.componentRef.setInput('document', {
      ...oneShot,
      one_shot_step: 'revise',
      stages: [
        { key: 'research', label: 'Research', model: 'm', status: 'completed', message: 'Done' },
        { key: 'resume', label: 'Resume', model: 'm', status: 'running', message: 'Fitting' },
      ],
    });
    await fixture.whenStable();
    expect(
      [...element.querySelectorAll('.call-steps li')].map((step) =>
        step.getAttribute('data-state'),
      ),
    ).toEqual(['done', 'done', 'done', 'done']);
    expect(element.querySelector('.current-stage')?.textContent).toContain('Resume');
  });
});
