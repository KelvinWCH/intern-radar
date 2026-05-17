import { Location } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { navigationItems } from './shared/constants/navigation.constants';
import { WorkspaceAtmosphere } from './shared/workspace-atmosphere/workspace-atmosphere';

@Component({
  imports: [RouterLink, RouterLinkActive, RouterOutlet, WorkspaceAtmosphere],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
  host: { '[class.wide-workspace]': 'wideWorkspace()' },
})
export class App {
  private readonly router = inject(Router);
  protected readonly title = 'Intern Radar';
  protected readonly navigation = navigationItems;
  protected readonly menuOpen = signal(false);
  protected readonly navigating = computed((): boolean => this.router.currentNavigation() !== null);
  // the jobs page uses the full window width
  protected readonly wideWorkspace = signal(inject(Location).path().split(/[?#]/)[0] === '/jobs');

  constructor() {
    this.router.events.pipe(takeUntilDestroyed()).subscribe((event): void => {
      if (!(event instanceof NavigationEnd)) {
        return;
      }
      this.wideWorkspace.set(event.urlAfterRedirects.split(/[?#]/)[0] === '/jobs');
      this.menuOpen.set(false);
    });
  }
}
