import { HttpClient } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  computed,
  inject,
  input,
  model,
  output,
  signal,
} from '@angular/core';
import type { OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import type { Subscription } from 'rxjs';
import { map } from 'rxjs';
import type { AiModelOptions, AiOptionsEdit } from '../../shared/models/ai.models';
import { parseAiOptions, reasoningEfforts, validAiOptions } from '../../shared/models/ai.models';
import { ModelCatalog } from '../../shared/model-catalog';
import { AiDefaults } from '../../settings/ai-defaults';
import type { AiTask } from '../../settings/ai-defaults';

@Component({
  selector: 'app-ai-options',
  imports: [FormsModule, SelectModule, InputNumberModule],
  templateUrl: './ai-options.html',
  styleUrl: './ai-options.scss',
})
export class AiOptions implements OnInit {
  readonly options = model<AiModelOptions>({});
  readonly disabled = input(false);
  readonly idPrefix = input('tailor');
  readonly label = input('AI model');
  readonly modelLabel = input<string>();
  readonly task = input<AiTask>('resume');
  readonly edited = output<AiOptionsEdit>();
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly catalogLoading = signal(true);
  protected readonly catalogError = signal('');
  protected readonly customModel = signal(false);
  private readonly models = signal<string[]>([]);
  protected readonly modelChoices = computed((): string[] => {
    const current = this.options().model;
    return [...new Set([...this.models(), ...(current ? [current] : [])])].sort();
  });
  protected readonly valid = validAiOptions;
  protected readonly efforts = [...reasoningEfforts];
  private readonly http = inject(HttpClient);
  private readonly catalog = inject(ModelCatalog);
  private readonly preferences = inject(AiDefaults);
  private readonly destroyRef = inject(DestroyRef);
  private catalogRequest: Subscription | undefined;

  ngOnInit(): void {
    this.loadModels();
    this.http
      .get<unknown>('/api/resumes/ai-settings')
      .pipe(map(parseAiOptions), takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (options): void => {
          const current = this.preferences.resolve(this.task(), this.options());
          this.options.set({ ...options, ...current });
          this.loading.set(false);
        },
        error: (): void => {
          this.options.set(this.preferences.resolve(this.task(), this.options()));
          this.loading.set(false);
          this.error.set(
            'Could not load model defaults. Blank fields use the server configuration.',
          );
        },
      });
  }

  protected loadModels(): void {
    this.catalogRequest?.unsubscribe();
    this.catalogLoading.set(true);
    this.catalogError.set('');
    this.catalogRequest = this.catalog
      .load()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (catalog): void => {
          this.models.set([...catalog.models]);
          this.catalogError.set(catalog.warning ?? '');
          this.catalogLoading.set(false);
        },
        error: (): void => {
          const remembered = this.catalog.remembered();
          if (remembered.length) {
            this.models.set(remembered);
          }
          this.catalogError.set(
            remembered.length
              ? 'Could not refresh available models. Showing the last loaded models.'
              : 'Could not load available models. The configured default is still available.',
          );
          this.catalogLoading.set(false);
        },
      });
  }

  apply(edit: AiOptionsEdit): void {
    if (edit.field === 'model') {
      this.setModel(edit.value);
      return;
    }
    this.options.update((options): AiModelOptions => ({
      ...options,
      [edit.field]: edit.value,
    }));
  }

  protected choose(edit: AiOptionsEdit): void {
    this.apply(edit);
    this.edited.emit(edit);
  }

  private setModel(value: string | null): void {
    const trimmed = value?.trim() ?? '';
    const selected = trimmed.length > 0 ? trimmed : null;
    if (selected === (this.options().model ?? null)) {
      return;
    }
    this.options.update((options): AiModelOptions => ({
      ...options,
      model: selected,
    }));
  }
}
