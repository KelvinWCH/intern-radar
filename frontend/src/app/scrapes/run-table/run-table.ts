import { DatePipe, DecimalPipe, TitleCasePipe } from '@angular/common';
import { Component, input, signal } from '@angular/core';
import { FailureDetailsPanel } from '../failure-details/failure-details';
import type { ScrapeRun } from '../models/scrape.models';
import { duration } from '../models/scrape.models';
import { scrapeTriggerLabel } from '../models/trigger.models';
@Component({
  selector: 'app-run-table',
  imports: [DatePipe, DecimalPipe, TitleCasePipe, FailureDetailsPanel],
  templateUrl: './run-table.html',
  styles: `
    .run-row {
      cursor: pointer;
    }
    .run-row.open {
      background: #f5f9f5;
    }
    .run-source {
      max-width: 260px;
      overflow-wrap: anywhere;
    }
    .run-source strong {
      display: block;
      font-weight: 500;
    }
    .started {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .zero {
      color: var(--muted);
    }
    .new:not(.zero) {
      color: var(--accent);
      font-weight: 600;
    }
    .toggle-cell {
      width: 44px;
      text-align: right;
    }
    .row-toggle {
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }
    .row-toggle:hover {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .row-toggle .pi {
      transition: transform 200ms ease;
    }
    .open .row-toggle .pi {
      transform: rotate(180deg);
    }
    .detail-row > td {
      border-top: 0;
      background: #fbfcf9;
      font-size: 13px;
    }
    .run-times {
      display: flex;
      flex-wrap: wrap;
      gap: 4px 18px;
      color: var(--muted);
    }
    .run-times code {
      color: var(--text);
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 12px;
      margin: 12px 0;
    }
    .metrics span {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-top: 2px;
    }
  `,
})
export class RunTable {
  readonly runs = input.required<readonly ScrapeRun[]>();
  protected readonly duration = duration;
  protected readonly scrapeTriggerLabel = scrapeTriggerLabel;
  private readonly toggled = signal<ReadonlySet<string>>(new Set());

  protected isOpen(run: ScrapeRun): boolean {
    const failed = run.status === 'failed' || run.failureCount > 0;
    return this.toggled().has(run.id) !== failed;
  }

  protected toggle(run: ScrapeRun): void {
    this.toggled.update((ids): ReadonlySet<string> => {
      const next = new Set(ids);
      if (!next.delete(run.id)) {
        next.add(run.id);
      }
      return next;
    });
  }
}
