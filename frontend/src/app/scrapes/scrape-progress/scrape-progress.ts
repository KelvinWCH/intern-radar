import { Component, computed, input } from '@angular/core';
import { scrapeFlowStages, scrapePageLabels } from '../constants/page-progress.constants';
import type { ScrapeTask } from '../models/scrape.models';
import { isPageWorking, scrapePageProgress } from '../page-progress';

@Component({
  selector: 'app-scrape-progress',
  templateUrl: './scrape-progress.html',
  styleUrl: './scrape-progress.scss',
})
export class ScrapeProgress {
  readonly task = input<ScrapeTask | null>(null);
  protected readonly pages = computed(() => scrapePageProgress(this.task()));
  protected readonly labels = scrapePageLabels;
  protected readonly stages = scrapeFlowStages;
  protected readonly isPageWorking = isPageWorking;
  protected readonly active = computed(
    (): boolean => this.task()?.status === 'queued' || this.task()?.status === 'running',
  );
  protected readonly percent = computed((): number =>
    Math.max(0, Math.min(100, this.task()?.progress.percent ?? 0)),
  );
  protected readonly stageIndex = computed((): number => {
    const task = this.task();
    if (!task) {
      return -1;
    }
    if (task.status === 'completed') {
      return 3;
    }
    if (!this.active()) {
      return -1;
    }
    const phase = task.progress.phase;
    if (phase === 'checking cache') {
      return 1;
    }
    return this.stages.findIndex((stage): boolean => stage.phase === phase);
  });
}
