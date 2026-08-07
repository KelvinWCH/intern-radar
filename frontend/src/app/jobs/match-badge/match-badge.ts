import { Component, computed, input } from '@angular/core';
import type { JobMatch } from '../models/job.models';

export const matchLabels = {
  strong: 'Strong match',
  good: 'Good match',
  fair: 'Fair match',
  low: 'Low match',
} as const;

@Component({
  selector: 'app-match-badge',
  template: `@if (match(); as value) {
    <span class="match-badge" [attr.data-band]="value.band" [title]="reasons()"
      ><i class="pi pi-bolt"></i> {{ label() }} <span class="score">{{ value.score }}</span></span
    >
  }`,
  styleUrl: './match-badge.scss',
})
export class MatchBadge {
  readonly match = input<JobMatch | null | undefined>(null);
  protected readonly label = computed((): string => {
    const value = this.match();
    return value ? matchLabels[value.band] : '';
  });
  protected readonly reasons = computed((): string => this.match()?.reasons.join(' · ') ?? '');
}
