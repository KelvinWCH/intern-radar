import { Component, computed, effect, input, model, signal, viewChildren } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { AiModelOptions, AiOptionsEdit } from '../../shared/models/ai.models';
import { reasoningEfforts } from '../../shared/models/ai.models';
import { AiOptions } from '../ai-options/ai-options';
import { oneShotDefaults, saveTailoringMode } from '../constants/tailoring-mode.constants';
import type { TailoringMode } from '../models/document.models';

@Component({
  selector: 'app-stage-models',
  imports: [FormsModule, AiOptions],
  template: ` <section class="stage-models">
    <label for="research-company-url">Company website (optional)</label>
    <input
      id="research-company-url"
      type="url"
      placeholder="https://company.com/about"
      [disabled]="disabled()"
      [ngModel]="companyUrl()"
      (ngModelChange)="companyUrl.set($event)"
      [ngModelOptions]="{ standalone: true }"
    />
    <fieldset class="mode" [disabled]="disabled()">
      <legend>How to run it</legend>
      <label class="mode-choice" [class.selected]="mode() === 'staged'">
        <input
          type="radio"
          name="tailoring-mode"
          value="staged"
          [checked]="mode() === 'staged'"
          (change)="mode.set('staged')"
        />
        <span>
          <strong>Separate stages</strong>
          <small>A researcher, two writers and an independent reviewer, each its own call.</small>
        </span>
      </label>
      <label class="mode-choice" [class.selected]="mode() === 'one_shot'">
        <input
          type="radio"
          name="tailoring-mode"
          value="one_shot"
          [checked]="mode() === 'one_shot'"
          (change)="mode.set('one_shot')"
        />
        <span>
          <strong>One shot</strong>
          <small>One call researches, drafts, reviews its drafts, then revises them.</small>
        </span>
      </label>
    </fieldset>
    @if (mode() === 'one_shot') {
      <app-ai-options
        task="resume"
        idPrefix="one-shot"
        label="One-shot model"
        modelLabel="Model"
        [(options)]="oneShot"
        [disabled]="disabled()"
      />
      <p class="hint">
        Page fitting and PDF checks still run on the final documents. A redraft call happens only if
        a document fails those checks.
      </p>
    } @else {
      <app-ai-options
        task="resume"
        idPrefix="shared"
        label="All stages"
        modelLabel="Model"
        [(options)]="shared"
        (edited)="applyToStages($event)"
        [disabled]="disabled()"
      />
      <details class="per-stage">
        <summary>
          Per-stage settings
          @for (difference of differences(); track difference) {
            <span class="difference">{{ difference }}</span>
          }
        </summary>
        <p class="hint">Changes above apply to every stage; adjust one stage here.</p>
        <div class="stage">
          <h4>Research</h4>
          <app-ai-options
            #stage
            task="research"
            label="Research"
            modelLabel="Model"
            idPrefix="research"
            [(options)]="research"
            [disabled]="disabled()"
          />
        </div>
        <div class="stage">
          <h4>
            Resume
            @if (!includeResume()) {
              <small>not selected</small>
            }
          </h4>
          <app-ai-options
            #stage
            task="resume"
            idPrefix="tailor"
            label="Resume"
            modelLabel="Model"
            [(options)]="resume"
            [disabled]="disabled() || !includeResume()"
          />
        </div>
        <div class="stage">
          <h4>
            Cover letter
            @if (!includeLetter()) {
              <small>not selected</small>
            }
          </h4>
          <app-ai-options
            #stage
            task="letter"
            idPrefix="letter"
            label="Cover letter"
            modelLabel="Model"
            [(options)]="letter"
            [disabled]="disabled() || !includeLetter()"
          />
        </div>
        <div class="stage">
          <h4>Independent reviewer</h4>
          <app-ai-options
            #stage
            task="review"
            idPrefix="reviewer"
            label="Independent reviewer"
            modelLabel="Model"
            [(options)]="reviewer"
            [disabled]="disabled()"
          />
        </div>
      </details>
    }
  </section>`,
  styles: `
    .stage-models {
      margin: 12px 0 0;
      display: grid;
      gap: 10px;
    }
    label {
      font-size: 13px;
      color: var(--muted);
    }
    input {
      width: 100%;
      margin: -6px 0 2px;
      min-height: 44px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font: inherit;
      font-size: 14px;
      color: var(--text);
      background: white;
    }
    .per-stage {
      border-top: 1px solid var(--line);
      padding-top: 8px;
    }
    summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 13px;
      min-height: 24px;
    }
    .difference {
      display: block;
      margin: 2px 0 0 14px;
      font-size: 12px;
    }
    .hint {
      margin: 8px 0 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .stage + .stage {
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px dashed var(--line);
    }
    h4 {
      display: flex;
      gap: 8px;
      align-items: baseline;
      margin: 0 0 8px;
      color: var(--text);
      font-size: 13px;
      font-weight: 600;
    }
    h4 small {
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
    }
    .mode {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
      padding: 0;
      border: 0;
    }
    .mode legend {
      margin-bottom: 6px;
      font-size: 13px;
      font-weight: 600;
    }
    .mode-choice {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface);
      cursor: pointer;
    }
    .mode-choice.selected {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .mode-choice input {
      margin-top: 3px;
    }
    .mode-choice span {
      display: grid;
      gap: 2px;
    }
    .mode-choice small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    @media (max-width: 600px) {
      .mode {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class StageModels {
  readonly research = model<AiModelOptions>({});
  readonly resume = model<AiModelOptions>({});
  readonly letter = model<AiModelOptions>({});
  readonly reviewer = model<AiModelOptions>({});
  readonly companyUrl = model('');
  readonly mode = model<TailoringMode>('staged');
  readonly oneShot = model<AiModelOptions>({ ...oneShotDefaults });
  readonly disabled = input(false);
  readonly includeResume = input(true);
  readonly includeLetter = input(true);
  protected readonly shared = signal<AiModelOptions>({});
  private readonly stages = viewChildren<AiOptions>('stage');

  constructor() {
    effect((): void => {
      saveTailoringMode(this.mode());
    });
  }
  protected readonly differences = computed((): string[] => {
    const shared = this.shared();
    const stages: [string, AiModelOptions, boolean][] = [
      ['Research', this.research(), true],
      ['Resume', this.resume(), this.includeResume()],
      ['Cover letter', this.letter(), this.includeLetter()],
      ['Reviewer', this.reviewer(), true],
    ];
    return stages.flatMap(([name, options, included]): string[] => {
      if (!included) {
        return [];
      }
      const parts: string[] = [];
      if ((options.model ?? null) !== (shared.model ?? null)) {
        parts.push(options.model ?? 'server model');
      }
      if ((options.reasoning_effort ?? null) !== (shared.reasoning_effort ?? null)) {
        parts.push(
          `${
            reasoningEfforts.find((item): boolean => item.value === options.reasoning_effort)
              ?.label ?? 'Model default'
          } effort`,
        );
      }
      return parts.length ? [`${name}: ${parts.join(', ')}`] : [];
    });
  });

  protected applyToStages(edit: AiOptionsEdit): void {
    for (const stage of this.stages()) {
      stage.apply(edit);
    }
  }
}
