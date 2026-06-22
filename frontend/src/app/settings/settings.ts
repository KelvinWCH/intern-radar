import { DOCUMENT } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ModelDefaults } from './model-defaults/model-defaults';
import { SignInSession } from '../sign-in/sign-in-session';

@Component({
  selector: 'app-settings',
  imports: [ModelDefaults],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings {
  private readonly session = inject(SignInSession);
  private readonly browser = inject(DOCUMENT).defaultView;
  protected readonly signedIn = this.session.token() !== null;

  protected signOut(): void {
    this.session.clear();
    this.browser?.location.assign('/sign-in');
  }
}
