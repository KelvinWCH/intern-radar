import { Component, input } from '@angular/core';
import type { FailureDetails } from '../models/failure.models';

@Component({
  selector: 'app-failure-details',
  template: `
    @if (error()) {
      <p class="notice error">{{ error() }}</p>
    }
    @if (details(); as data) {
      @if (data.failureCount) {
        <p>
          {{ data.failureCount }} failed operation{{ data.failureCount === 1 ? '' : 's' }} recorded.
        </p>
      }
      <ul>
        @for (failure of data.failures; track $index) {
          <li>
            <strong>{{ failure.stage }} · {{ failure.error_type }}</strong>
            <p>{{ failure.reason }}</p>
            @if (failure.url) {
              <a [href]="failure.url" target="_blank" rel="noopener noreferrer">{{
                failure.url
              }}</a>
            }
          </li>
        }
      </ul>
      @if (data.failuresOmitted) {
        <p>{{ data.failuresOmitted }} additional failures omitted from this report.</p>
      }
      @if (data.failureCount && !data.failures.length && !error()) {
        <p>Individual failure reasons were not recorded for this older attempt.</p>
      }
    }
  `,
  styles: `
    :host {
      display: block;
      overflow-wrap: anywhere;
    }
    ul {
      padding-left: 20px;
    }
    li {
      margin: 12px 0;
    }
    li p {
      white-space: pre-wrap;
      margin: 6px 0;
    }
    a {
      color: var(--accent);
    }
  `,
})
export class FailureDetailsPanel {
  readonly details = input<FailureDetails | null>(null);
  readonly error = input<string | null>(null);
}
