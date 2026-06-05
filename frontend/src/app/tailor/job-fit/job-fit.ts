import { Component, computed, input } from '@angular/core';
import type { PdfDiagnostics } from '../models/application-review.models';
import type { RequirementMatch } from '../models/resume.models';

@Component({
  selector: 'app-job-fit',
  templateUrl: './job-fit.html',
  styleUrl: './job-fit.scss',
})
export class JobFit {
  readonly coverage = input<readonly RequirementMatch[]>([]);
  readonly checks = input<PdfDiagnostics | null>(null);
  protected readonly keywordCount = computed((): number => {
    const checks = this.checks();
    return checks
      ? checks.matched_keywords.length +
          checks.missing_supported_keywords.length +
          checks.unsupported_keywords.length
      : 0;
  });
  protected readonly covered = computed(() =>
    this.coverage().filter((item) => item.entries.length),
  );
  protected readonly uncovered = computed(() =>
    this.coverage().filter((item) => !item.entries.length),
  );
}
