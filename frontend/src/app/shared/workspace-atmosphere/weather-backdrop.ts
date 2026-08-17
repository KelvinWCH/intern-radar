import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { weatherDefinitions, weatherStorageKey } from './constants/weather.constants';
import type { WeatherParticle, WeatherScene } from './models/weather.models';
import { WeatherVisitors } from './weather-visitors';

@Component({
  imports: [WeatherVisitors],
  selector: 'app-weather-backdrop',
  templateUrl: './weather-backdrop.html',
  styleUrl: './weather-backdrop.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WeatherBackdrop {
  private readonly document = inject(DOCUMENT);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private hasNavigated = this.router.navigated;
  protected readonly weather = signal(this.createScene(0, this.previousWeather()));

  constructor() {
    this.router.events.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((event): void => {
      if (!(event instanceof NavigationEnd)) {
        return;
      }
      if (this.hasNavigated) {
        const previous = this.weather();
        this.weather.set(this.createScene(previous.revision + 1, previous.kind));
      }
      this.hasNavigated = true;
    });
  }

  private previousWeather(): string | null {
    try {
      return this.document.defaultView?.sessionStorage.getItem(weatherStorageKey) ?? null;
    } catch {
      return null;
    }
  }

  private createScene(revision: number, previous: string | null): WeatherScene {
    const available = weatherDefinitions.filter((weather): boolean => weather.kind !== previous);
    const definition =
      available[Math.floor(Math.random() * available.length)] ?? weatherDefinitions[0];
    if (!definition) {
      return { revision, kind: 'sunny', particles: [], visitor: null };
    }
    const visitor =
      definition.visitors[Math.floor(Math.random() * definition.visitors.length)] ?? null;
    const particles = Array.from(
      { length: definition.particleCount },
      (_, index): WeatherParticle => ({
        leftPercent: ((index + Math.random()) / definition.particleCount) * 110,
        delaySeconds: -Math.random() * definition.fallDurationSeconds,
        durationSeconds: definition.fallDurationSeconds * (0.8 + Math.random() * 0.4),
        sizePixels: 4 + Math.random() * 4,
        opacity: 0.35 + Math.random() * 0.3,
      }),
    );
    try {
      this.document.defaultView?.sessionStorage.setItem(weatherStorageKey, definition.kind);
    } catch {
      // session storage can be blocked, thats fine
    }
    return { revision, kind: definition.kind, particles, visitor };
  }
}
