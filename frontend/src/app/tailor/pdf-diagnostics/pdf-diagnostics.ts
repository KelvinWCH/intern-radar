import { Component, input } from '@angular/core';
import type { PdfDiagnosticCheck, PdfDiagnostics } from '../models/application-review.models';

@Component({
  selector: 'app-pdf-diagnostics',
  templateUrl: './pdf-diagnostics.html',
  styleUrl: './pdf-diagnostics.scss',
})
export class PdfDiagnosticsPanel {
  readonly reports = input.required<readonly PdfDiagnostics[]>();

  protected count(report: PdfDiagnostics, status: PdfDiagnosticCheck['status']): number {
    return report.checks.filter((check) => check.status === status).length;
  }
}
