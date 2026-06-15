import { DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { jobSourceLabels } from '../constants/job-source.constants';
import type { JobSummary } from '../models/job.models';

@Component({
  selector: 'app-related-postings',
  imports: [DatePipe, RouterLink],
  templateUrl: './related-postings.html',
  styleUrl: './related-postings.scss',
})
export class RelatedPostings {
  readonly postings = input.required<readonly JobSummary[]>();
  protected readonly sourceLabels = jobSourceLabels;
}
