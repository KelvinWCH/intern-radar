import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

@Component({
  selector: 'app-profile-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile-section.html',
  styleUrl: './profile-section.scss',
})
export class ProfileSection {
  readonly heading = input.required<string>();
  readonly icon = input.required<string>();
  readonly summary = input('');
  readonly count = input<number | null>(null);
  readonly attention = input(false);
  readonly open = model(false);

  protected toggled(event: Event): void {
    if (event.target instanceof HTMLDetailsElement && event.target.open !== this.open()) {
      this.open.set(event.target.open);
    }
  }
}
