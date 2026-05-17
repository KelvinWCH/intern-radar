import { DecimalPipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { ScrapeSummaryState } from '../../scrapes/models/scrape-summary.models';
import { duration } from '../../scrapes/models/scrape.models';
import { formatTokens } from '../../shared/usage-format';

@Component({
  selector: 'app-daily-statistics',
  imports: [DecimalPipe, RouterLink],
  templateUrl: './daily-statistics.html',
  styleUrl: './daily-statistics.scss',
})
export class DailyStatistics {
  readonly state = input.required<ScrapeSummaryState>();
  protected readonly formatTokens = formatTokens;
  protected readonly duration = duration;
}
