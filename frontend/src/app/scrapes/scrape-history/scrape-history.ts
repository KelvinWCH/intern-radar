import { DatePipe, TitleCasePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import type { Subscription } from 'rxjs';
import { apiError } from '../../shared/api-error';
import { CursorNavigation } from '../../shared/pagination';
import type { ScrapeHistoryPage, ScrapeTask } from '../models/scrape.models';
import { duration } from '../models/scrape.models';
import { RunTable } from '../run-table/run-table';
import { ScrapesService } from '../scrapes.service';
@Component({
  selector: 'app-scrape-history',
  imports: [FormsModule, DatePipe, TitleCasePipe, RunTable],
  templateUrl: './scrape-history.html',
  styles: `
    .task-list {
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
    }
    summary {
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      flex-wrap: wrap;
      font-size: 13px;
    }
    .task-list > .panel {
      padding: 10px 14px;
    }
    .attempts-head {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 10px;
      padding: 10px 14px;
    }
    .attempts-head h3 {
      margin: 0 auto 0 0;
      font-size: 17px;
      font-weight: 600;
    }
    .attempts-head input,
    .attempts-head select {
      min-height: 34px;
      padding: 5px 10px;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: white;
      color: var(--text);
      font-size: 14px;
    }
    .attempts-head input {
      width: min(260px, 100%);
    }
    .empty-page {
      padding: 0 14px;
    }
    .task-meta {
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
      margin: 12px 0;
    }
  `,
})
export class ScrapeHistory {
  private readonly scrapesService = inject(ScrapesService);
  private readonly destroyRef = inject(DestroyRef);
  private historySubscription: Subscription | undefined;
  private tasksSubscription: Subscription | undefined;
  protected readonly historyNavigation = new CursorNavigation();
  private historyFilterKey = '';
  protected readonly historyPage = signal<ScrapeHistoryPage | null>(null);
  protected readonly scrapeTasks = signal<readonly ScrapeTask[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly duration = duration;
  protected source = '';
  protected status = '';
  constructor() {
    this.loadTasks();
    this.load();
  }
  protected load(requestedOffset = 0, refresh = false): void {
    const key = JSON.stringify([this.source.trim(), this.status]);
    // new filters start again from the first page
    const offset = key === this.historyFilterKey ? requestedOffset : 0;
    if (offset === 0) {
      this.historyFilterKey = key;
      this.historyNavigation.reset();
    }
    const cursor = this.historyNavigation.cursor(offset);
    if (cursor === undefined) {
      return;
    }
    this.historySubscription?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    if (refresh) {
      this.loadTasks();
    }
    this.historySubscription = this.scrapesService
      .history(offset, this.source.trim(), this.status, cursor)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (page): void => {
          this.historyNavigation.remember(page);
          this.historyPage.set(page);
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not read scrape history.'));
        },
      });
  }

  private loadTasks(): void {
    this.tasksSubscription?.unsubscribe();
    this.tasksSubscription = this.scrapesService
      .tasks()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (tasks): void => {
          this.scrapeTasks.set(tasks);
        },
        error: (error: unknown): void => {
          this.error.set(apiError(error, 'Could not read recent scrape requests.'));
        },
      });
  }
}
