import { DatePipe } from '@angular/common';
import type { ElementRef } from '@angular/core';
import { Component, afterRenderEffect, computed, inject, signal, viewChild } from '@angular/core';
import { scrapeStepLabels } from '../constants/console.constants';
import type { ScrapeStepKind } from '../models/console.models';
import type { ScrapeEvent, ScrapeRun } from '../models/scrape.models';
import { scrapeTriggerLabel } from '../models/trigger.models';
import { ScrapeStatusStore } from '../scrape-status.store';
import { ScrapeProgress } from '../scrape-progress/scrape-progress';

export function stepKind(event: ScrapeEvent): ScrapeStepKind {
  const message = event.message;
  if (event.level === 'error') {
    return 'error';
  }
  if (event.level === 'warning' || message.startsWith('Skipping')) {
    return 'skip';
  }
  if (message.startsWith('Starting')) {
    return 'start';
  }
  if (message.startsWith('Fetching') || message.startsWith('Listing')) {
    return 'fetch';
  }
  if (message.startsWith('Downloading')) {
    return 'download';
  }
  if (message.startsWith('Using saved') || message.startsWith('Reusing saved')) {
    return 'cache';
  }
  if (message.includes('Chrome')) {
    return 'browser';
  }
  if (message.startsWith('Sending')) {
    return 'ai';
  }
  if (message.startsWith('Extracted') || message.startsWith('No matching job')) {
    return 'extract';
  }
  if (message.startsWith('Saving')) {
    return 'save';
  }
  if (message.startsWith('Finished')) {
    return 'done';
  }
  return 'info';
}

@Component({
  selector: 'app-scrape-console',
  imports: [DatePipe, ScrapeProgress],
  templateUrl: './scrape-console.html',
  styleUrls: ['./scrape-console.scss', './scrape-workspace.scss'],
})
export class ScrapeConsole {
  protected readonly task = inject(ScrapeStatusStore).task;
  protected readonly activity = inject(ScrapeStatusStore).activity;
  protected readonly external = inject(ScrapeStatusStore).external;
  protected readonly events = computed((): readonly ScrapeEvent[] =>
    this.external() ? (this.activity()?.events ?? []) : (this.task()?.events ?? []),
  );
  protected readonly runs = computed((): readonly ScrapeRun[] =>
    this.external() ? (this.activity()?.runs ?? []) : (this.task()?.runs ?? []),
  );
  protected readonly scrapeTriggerLabel = scrapeTriggerLabel;
  protected readonly follow = signal(true);
  protected readonly scrapeStepLabels = scrapeStepLabels;
  protected readonly stepKind = stepKind;
  protected readonly active = computed(
    (): boolean =>
      this.external() || this.task()?.status === 'queued' || this.task()?.status === 'running',
  );
  protected readonly sources = computed(
    (): ReadonlyMap<string, string> =>
      new Map(this.runs().map((run): [string, string] => [run.id, run.source])),
  );
  private readonly log = viewChild<ElementRef<HTMLElement>>('log');

  constructor() {
    afterRenderEffect((): void => {
      this.events();
      const element = this.log()?.nativeElement;
      if (element && this.follow()) {
        element.scrollTop = element.scrollHeight;
      }
    });
  }
}
