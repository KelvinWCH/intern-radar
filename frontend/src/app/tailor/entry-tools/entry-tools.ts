import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-entry-tools',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button
      type="button"
      class="text-button"
      title="Move up"
      [disabled]="index() === 0"
      (click)="move(-1)"
    >
      <i class="pi pi-arrow-up"></i></button
    ><button
      type="button"
      class="text-button"
      title="Move down"
      [disabled]="index() === items().length - 1"
      (click)="move(1)"
    >
      <i class="pi pi-arrow-down"></i></button
    ><button type="button" class="text-button" title="Remove" (click)="remove()">
      <i class="pi pi-trash"></i>
    </button>`,
  styles: `
    :host {
      display: inline-flex;
      flex: none;
      gap: 2px;
    }
  `,
})
export class EntryTools {
  readonly items = input.required<unknown[]>();
  readonly index = input.required<number>();
  readonly name = input.required<string>();
  readonly changed = output();

  protected move(offset: -1 | 1): void {
    const items = this.items();
    const index = this.index();
    const target = index + offset;
    if (target < 0 || target >= items.length) {
      return;
    }
    const [item] = items.splice(index, 1);
    items.splice(target, 0, item);
    this.changed.emit();
  }

  protected remove(): void {
    this.items().splice(this.index(), 1);
    this.changed.emit();
  }
}
