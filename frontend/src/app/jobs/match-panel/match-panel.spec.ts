import { TestBed } from '@angular/core/testing';
import type { JobMatch } from '../models/job.models';
import { MatchPanel } from './match-panel';

const match: JobMatch = {
  score: 88,
  band: 'strong',
  reasons: ['Close to Software Engineering Intern', 'Uses React, Python', 'In Toronto'],
  skills: ['React', 'Python'],
  role: 'Software Engineering Intern',
  components: { role: 0.96, background: 0.9, skills: 0.62, location: 1, student: 1 },
  scoredAt: Date.UTC(2026, 9, 22, 15) / 1000,
};

describe('MatchPanel and MatchBadge', (): void => {
  it('explains the score', async (): Promise<void> => {
    const fixture = TestBed.createComponent(MatchPanel);
    fixture.componentRef.setInput('match', match);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.match-score')?.textContent.trim()).toBe('88');
    expect(element.textContent).toContain('Strong match');
    expect(element.textContent).toContain('Closest to Software Engineering Intern');
    expect(
      Array.from(element.querySelectorAll('.match-reasons li'), (item) => item.textContent),
    ).toEqual(match.reasons);
    const labels = Array.from(element.querySelectorAll('.match-parts dt'), (item) =>
      item.textContent.trim(),
    );
    expect(labels).toEqual(['Role', 'Background', 'Skills', 'Location']);
    expect(element.querySelectorAll('.skill-chip')).toHaveLength(2);
  });
});
