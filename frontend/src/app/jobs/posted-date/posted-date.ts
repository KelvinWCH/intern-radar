import { DatePipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

@Component({
  selector: 'app-posted-date',
  imports: [DatePipe],
  template: `
    @let value = timestamp();
    @if (value === null || value === undefined) {
      <span title="The source did not provide a posting date">Posted date unknown</span>
    } @else {
      <span title="When the employer or job board says this job was posted">
        Posted
        <time [attr.datetime]="value * 1000 | date: 'yyyy-MM-dd' : timezone()">{{
          value * 1000 | date: 'MMM d, y' : timezone()
        }}</time>
      </span>
    }
  `,
})
export class PostedDate {
  readonly timestamp = input<number | null | undefined>(null);
  protected readonly timezone = computed((): string | undefined => {
    const value = this.timestamp();
    return value != null && value % 86_400 === 0 ? 'UTC' : undefined;
  });
}
