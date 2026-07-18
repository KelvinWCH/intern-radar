import { Component, input } from '@angular/core';

@Component({
  selector: 'app-skeleton',
  template: '',
  styleUrl: './skeleton.scss',
  host: { '[style.width]': 'width()', '[style.height]': 'height()' },
})
export class Skeleton {
  readonly width = input('100%');
  readonly height = input('1em');
}
