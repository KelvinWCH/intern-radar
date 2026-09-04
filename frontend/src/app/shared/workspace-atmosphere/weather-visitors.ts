import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { backgroundFlock } from './constants/weather.constants';
import type { WeatherVisitorKind } from './models/weather.models';

@Component({
  selector: 'app-weather-visitors',
  templateUrl: './weather-visitors.html',
  styleUrl: './weather-visitors.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.data-visitor]': 'kind()' },
})
export class WeatherVisitors {
  readonly kind = input.required<WeatherVisitorKind>();
  protected readonly flock = backgroundFlock;
}
