import { Component, booleanAttribute, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { QuickGenerateJob, QuickGenerateState } from '../models/quick-generate.models';
import { QuickGenerateStore } from './quick-generate.store';

@Component({
  selector: 'app-quick-generate',
  imports: [RouterLink],
  templateUrl: './quick-generate.html',
  styleUrl: './quick-generate.scss',
  host: { '[class.compact]': 'compact()' },
})
export class QuickGenerate {
  readonly job = input.required<QuickGenerateJob>();
  readonly compact = input(false, { transform: booleanAttribute });
  private readonly store = inject(QuickGenerateStore);
  protected readonly state = computed((): QuickGenerateState => this.store.state(this.job().id));
  protected readonly error = computed((): string => {
    const state = this.state();
    return state.status === 'failed' ? state.error : '';
  });

  protected start(): void {
    this.store.start(this.job());
  }
}
