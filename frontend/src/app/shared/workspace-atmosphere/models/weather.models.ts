export type WeatherKind =
  | 'sunny'
  | 'snow'
  | 'rain'
  | 'thunderstorm'
  | 'fog'
  | 'hail'
  | 'cloudy'
  | 'breeze'
  | 'ocean'
  | 'sunset';

export type WeatherVisitorKind = 'plane' | 'fish' | 'balloon';

export interface WeatherDefinition {
  readonly kind: WeatherKind;
  readonly particleCount: number;
  readonly fallDurationSeconds: number;
  readonly visitors: readonly WeatherVisitorKind[];
}

export interface WeatherParticle {
  readonly leftPercent: number;
  readonly delaySeconds: number;
  readonly durationSeconds: number;
  readonly sizePixels: number;
  readonly opacity: number;
}

export interface WeatherScene {
  readonly revision: number;
  readonly kind: WeatherKind;
  readonly particles: readonly WeatherParticle[];
  readonly visitor: WeatherVisitorKind | null;
}
