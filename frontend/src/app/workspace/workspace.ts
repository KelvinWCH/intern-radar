import { Component } from '@angular/core';
import { DailyReport } from '../jobs/daily-report/daily-report';
import { ScrapeConsole } from '../scrapes/scrape-console/scrape-console';
import { ScrapeControls } from '../scrapes/scrape-controls/scrape-controls';

@Component({
  selector: 'app-workspace',
  imports: [DailyReport, ScrapeControls, ScrapeConsole],
  templateUrl: './workspace.html',
  styleUrl: './workspace.scss',
})
export class Workspace {}
