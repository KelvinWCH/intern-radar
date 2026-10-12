import { Component, input } from '@angular/core';
import { jobSourceLabels } from '../constants/job-source.constants';
import type { SourceType } from '../models/job.models';

@Component({
  selector: 'app-source-badge',
  templateUrl: './source-badge.html',
  styleUrl: './source-badge.scss',
})
export class SourceBadge {
  readonly source = input.required<SourceType>();
  protected readonly sourceLabels = jobSourceLabels;
}
