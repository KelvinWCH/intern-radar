import { DOCUMENT } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';

@Component({
  selector: 'app-loading-indicator',
  templateUrl: './loading-indicator.html',
  styleUrl: './loading-indicator.scss',
  host: { '[class.is-compact]': 'compact()', '[class.is-paused]': 'paused()' },
})
export class LoadingIndicator {
  readonly label = input('Loading...');
  readonly detail = input('');
  readonly compact = input(false);
  private readonly document = inject(DOCUMENT);
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly destroyRef = inject(DestroyRef);
  private readonly visible = signal(true);
  private readonly hidden = signal(this.document.hidden);
  protected readonly paused = computed((): boolean => !this.visible() || this.hidden());

  constructor() {
    afterNextRender((): void => {
      const updateVisibility = (): void => {
        this.hidden.set(this.document.hidden);
      };
      this.document.addEventListener('visibilitychange', updateVisibility);
      const observer =
        typeof IntersectionObserver === 'undefined'
          ? null
          : new IntersectionObserver((entries): void => {
              this.visible.set(entries.some((entry): boolean => entry.isIntersecting));
            });
      observer?.observe(this.element.nativeElement);
      this.destroyRef.onDestroy((): void => {
        observer?.disconnect();
        this.document.removeEventListener('visibilitychange', updateVisibility);
      });
    });
  }
}
