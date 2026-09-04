import type { WeatherDefinition } from '../models/weather.models';

export const weatherStorageKey = 'intern-radar.workspace-weather';

export const weatherDefinitions: readonly WeatherDefinition[] = [
  {
    kind: 'sunny',
    particleCount: 0,
    fallDurationSeconds: 0,
    visitors: ['plane', 'balloon'],
  },
  { kind: 'snow', particleCount: 56, fallDurationSeconds: 19, visitors: [] },
  { kind: 'rain', particleCount: 72, fallDurationSeconds: 3.6, visitors: [] },
  { kind: 'thunderstorm', particleCount: 64, fallDurationSeconds: 3, visitors: [] },
  { kind: 'fog', particleCount: 0, fallDurationSeconds: 0, visitors: [] },
  { kind: 'hail', particleCount: 44, fallDurationSeconds: 3.8, visitors: [] },
  { kind: 'cloudy', particleCount: 0, fallDurationSeconds: 0, visitors: ['plane'] },
  { kind: 'breeze', particleCount: 24, fallDurationSeconds: 24, visitors: ['balloon'] },
  { kind: 'ocean', particleCount: 16, fallDurationSeconds: 26, visitors: ['fish'] },
  {
    kind: 'sunset',
    particleCount: 0,
    fallDurationSeconds: 0,
    visitors: ['plane', 'balloon'],
  },
];

export const backgroundFlock = [0, 1, 2, 3, 4] as const;
