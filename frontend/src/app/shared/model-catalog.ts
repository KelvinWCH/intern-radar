import { DOCUMENT } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs';
import * as validation from './api-validation';
import type { ModelChoices } from './models/ai.models';

const storageKey = 'intern-radar.ai-models.v1';

@Injectable({ providedIn: 'root' })
export class ModelCatalog {
  private readonly http = inject(HttpClient);
  private readonly browser = inject(DOCUMENT).defaultView;

  load(): Observable<ModelChoices> {
    return this.http.get<unknown>('/api/resumes/ai-models').pipe(
      map((value): ModelChoices => {
        const row = validation.object(value);
        const models = validation.list(row['models'], validation.text);
        if (models.some((model): boolean => !model.trim() || model.length > 200)) {
          throw new Error('Invalid model catalog.');
        }
        const warning = validation.optionalText(row['warning'] ?? null);
        if (warning === null) {
          this.remember(models);
          return { models, warning };
        }
        const remembered = this.remembered();
        return remembered.length
          ? {
              models: [...new Set([...models, ...remembered])],
              warning: 'Could not refresh the model list. Showing the last loaded models.',
            }
          : { models, warning };
      }),
    );
  }

  remembered(): string[] {
    try {
      const saved: unknown = JSON.parse(this.browser?.localStorage.getItem(storageKey) ?? '[]');
      return Array.isArray(saved)
        ? saved.filter(
            (model: unknown): model is string =>
              typeof model === 'string' && !!model.trim() && model.length <= 200,
          )
        : [];
    } catch {
      return [];
    }
  }

  private remember(models: readonly string[]): void {
    if (models.length < 2) {
      return;
    }
    try {
      this.browser?.localStorage.setItem(storageKey, JSON.stringify(models));
    } catch {
      // storage blocked, we just wont remember the list
    }
  }
}
