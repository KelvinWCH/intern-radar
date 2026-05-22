import { Component } from '@angular/core';
import { WeatherBackdrop } from './weather-backdrop';

@Component({
  imports: [WeatherBackdrop],
  selector: 'app-workspace-atmosphere',
  templateUrl: './workspace-atmosphere.html',
  styleUrl: './workspace-atmosphere.scss',
})
export class WorkspaceAtmosphere {}
