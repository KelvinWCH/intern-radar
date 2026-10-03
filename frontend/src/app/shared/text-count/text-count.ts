import { DecimalPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { countCharacters } from '../text-count';

@Component({
  selector: 'app-text-count',
  imports: [DecimalPipe],
  template: `
    <div class="counts" [class.over-limit]="count() > limit()">
      <span>{{ count() | number }} / {{ limit() | number }} characters</span>
      <span>{{ words() | number }} words</span>
    </div>
    <div class="meter"><span [style.width.%]="percentage()"></span></div>
    @if (count() > limit()) {
      <p class="warning">
        {{ count() - limit() | number }} characters over the {{ purpose() }} limit. {{ guidance() }}
      </p>
    }
  `,
  styles: `
    :host {
      display: block;
      margin-top: 7px;
      font-size: 12px;
      color: var(--muted);
    }
    .counts {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 4px 12px;
      font-variant-numeric: tabular-nums;
    }
    .meter {
      height: 3px;
      background: var(--line);
      border-radius: 4px;
      overflow: hidden;
      margin-top: 6px;
    }
    .meter span {
      display: block;
      height: 100%;
      background: var(--accent);
    }
    .over-limit,
    .warning {
      color: #a53241;
    }
    .over-limit + .meter span {
      background: #a53241;
    }
    .warning {
      margin: 6px 0 0;
      line-height: 1.5;
    }
  `,
})
export class TextCount {
  readonly text = input('');
  readonly limit = input.required<number>();
  readonly purpose = input('saving');
  readonly guidance = input('Shorten this text before continuing.');
  protected readonly count = computed((): number => countCharacters(this.text()));
  protected readonly words = computed((): number => this.text().match(/\S+/gu)?.length ?? 0);
  protected readonly percentage = computed((): number =>
    Math.min(100, (this.count() / this.limit()) * 100),
  );
}
