import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';
import { map } from 'rxjs';
import { parseAiOptions } from '../../shared/models/ai.models';
import { ModelCatalog } from '../../shared/model-catalog';
import { AiDefaults, aiTasks, emptySettings, recommendedModels } from '../ai-defaults';
import type { AiDefaultsSettings } from '../ai-defaults';

@Component({
  selector: 'app-model-defaults',
  imports: [FormsModule, SelectModule],
  templateUrl: './model-defaults.html',
  styleUrl: './model-defaults.scss',
})
export class ModelDefaults {
  private readonly preferences = inject(AiDefaults);
  private readonly http = inject(HttpClient);
  private readonly catalog = inject(ModelCatalog);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly draft = signal({ ...this.preferences.settings() });
  protected readonly groups = ['Documents', 'Writing assistance', 'Job discovery'];
  protected readonly tasks = aiTasks;
  protected readonly recommended = recommendedModels;
  protected readonly models = signal<string[]>([]);
  protected readonly loading = signal(false);
  protected readonly warning = signal('');
  protected readonly error = signal('');
  protected readonly saved = signal(false);
  protected readonly serverModel = signal('');
  protected readonly dirty = computed(
    (): boolean => JSON.stringify(this.draft()) !== JSON.stringify(this.preferences.settings()),
  );
  protected readonly overridden = computed(
    (): number => this.tasks.filter((task): boolean => !!this.draft()[task.id]).length,
  );
  protected readonly inheritedLabel = computed((): string => {
    const model = this.draft().default;
    return model ? `Use default · ${model}` : 'Use default';
  });
  protected readonly choices = computed((): string[] =>
    [
      ...new Set([
        ...this.models(),
        ...Object.values(this.draft()).filter((value): value is string => !!value),
      ]),
    ].sort(),
  );

  constructor() {
    this.loadModels();
    this.http
      .get<unknown>('/api/resumes/ai-settings')
      .pipe(map(parseAiOptions), takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (options): void => {
          this.serverModel.set(options.model ?? '');
        },
        error: (): void => {
          // keep the blank default if the server is down
        },
      });
  }

  protected loadModels(): void {
    if (this.loading()) {
      return;
    }
    this.loading.set(true);
    this.warning.set('');
    this.catalog
      .load()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (catalog): void => {
          this.models.set([...catalog.models]);
          this.warning.set(catalog.warning ?? '');
          this.loading.set(false);
        },
        error: (): void => {
          const remembered = this.catalog.remembered();
          if (remembered.length) {
            this.models.set(remembered);
          }
          this.warning.set(
            remembered.length
              ? 'The model list is unavailable right now. Showing the last loaded models.'
              : 'The model list is unavailable. You can still enter a provider model ID or keep your saved choices.',
          );
          this.loading.set(false);
        },
      });
  }

  protected change(key: keyof AiDefaultsSettings, value: string | null): void {
    this.draft.update((draft): AiDefaultsSettings => ({
      ...draft,
      [key]: value === '' ? null : value,
    }));
    this.saved.set(false);
    this.error.set('');
  }

  protected reset(): void {
    this.draft.set(emptySettings());
    this.saved.set(false);
    this.error.set('');
  }

  protected save(): void {
    this.error.set('');
    try {
      this.preferences.save(this.draft());
      this.draft.set({ ...this.preferences.settings() });
      this.saved.set(true);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Could not save model defaults.');
    }
  }
}
