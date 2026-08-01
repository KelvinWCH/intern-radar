import { provideHttpClient, withInterceptors } from '@angular/common/http';
import type { ApplicationConfig } from '@angular/core';
import { provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withInMemoryScrolling } from '@angular/router';
import { definePreset } from '@primeuix/themes';
import Aura from '@primeuix/themes/aura';
import { providePrimeNG } from 'primeng/config';
import { routes } from './app.routes';
import { signInInterceptor } from './sign-in/sign-in-session';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptors([signInInterceptor])),
    provideRouter(
      routes,
      withInMemoryScrolling({ scrollPositionRestoration: 'enabled', anchorScrolling: 'enabled' }),
    ),
    providePrimeNG({
      theme: {
        preset: definePreset(Aura, {
          semantic: {
            primary: {
              50: '#effaf3',
              100: '#d9f2e2',
              200: '#b4e3c7',
              300: '#83cda4',
              400: '#4fae7f',
              500: '#2c8d5f',
              600: '#1f6f4a',
              700: '#19593c',
              800: '#164832',
              900: '#133b2a',
              950: '#082117',
            },
          },
        }),
        options: { darkModeSelector: false },
      },
    }),
  ],
};
