import { DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { QuickGenerate } from '../../tailor/quick-generate/quick-generate';
import { DuplicatedJobsPanel } from '../duplicated-jobs/duplicated-jobs';
import type { JobSummary } from '../models/job.models';
import { PostedDate } from '../posted-date/posted-date';
import { SourceBadge } from '../source-badge/source-badge';

@Component({
  selector: 'app-job-card',
  imports: [DatePipe, RouterLink, DuplicatedJobsPanel, PostedDate, SourceBadge, QuickGenerate],
  templateUrl: './job-card.html',
  styleUrl: './job-card.scss',
})
export class JobCard {
  readonly job = input.required<JobSummary>();
}
