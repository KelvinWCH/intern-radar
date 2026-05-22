import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { matchLabels } from '../match-badge/match-badge';
import type { JobMatch } from '../models/job.models';

interface MatchPart {
  readonly key: string;
  readonly label: string;
  readonly help: string;
  readonly value: number;
}

const parts: readonly Omit<MatchPart, 'value'>[] = [
  { key: 'role', label: 'Role', help: 'How close the posting is to your closest target role' },
  {
    key: 'background',
    label: 'Background',
    help: 'How close the posting is to your skills, projects, and experience',
  },
  {
    key: 'skills',
    label: 'Skills',
    help: 'Your skills named in the posting, rarer ones counting more',
  },
  {
    key: 'location',
    label: 'Location',
    help: 'Your preferred cities, then the Toronto area, then Canada',
  },
  {
    key: 'feedback',
    label: 'Your picks',
    help: 'How close the posting is to jobs you saved, applied to, or tailored for',
  },
];

@Component({
  selector: 'app-match-panel',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './match-panel.html',
  styleUrl: './match-panel.scss',
})
export class MatchPanel {
  readonly match = input<JobMatch | null | undefined>(null);
  protected readonly label = computed((): string => {
    const value = this.match();
    return value ? matchLabels[value.band] : '';
  });
  protected readonly parts = computed((): readonly MatchPart[] => {
    const value = this.match();
    if (!value) {
      return [];
    }
    return parts.flatMap((part): MatchPart[] => {
      const score = value.components[part.key];
      return score === undefined ? [] : [{ ...part, value: score }];
    });
  });
}
