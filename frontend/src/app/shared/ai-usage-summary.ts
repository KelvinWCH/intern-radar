import { DecimalPipe } from '@angular/common';
import { Component, input } from '@angular/core';
import type { AiUsage } from './models/ai.models';

@Component({
  selector: 'app-ai-usage-summary',
  imports: [DecimalPipe],
  template: `
    @if (usage(); as value) {
      <p class="usage" title="Totals include revision attempts">
        <span>{{ value.model_name }}</span>
        <span>{{ value.calls }} AI {{ value.calls === 1 ? 'call' : 'calls' }}</span>
        <span
          >{{ value.input_tokens === null ? 'Unknown' : (value.input_tokens | number) }} tokens
          in</span
        >
        <span
          >{{ value.output_tokens === null ? 'Unknown' : (value.output_tokens | number) }} tokens
          out</span
        >
      </p>
    } @else {
      <p class="hint">AI usage not recorded for this version.</p>
    }
  `,
  styles: `
    .usage {
      display: flex;
      flex-wrap: wrap;
      gap: 0 6px;
      margin: 6px 0;
      font-size: 12px;
      line-height: 1.7;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .usage span + span::before {
      content: '·';
      margin-right: 6px;
    }
  `,
})
export class AiUsageSummary {
  readonly usage = input<AiUsage | null>();
}
