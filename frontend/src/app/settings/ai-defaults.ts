import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';
import type { AiModelOptions, ReasoningEffort } from '../shared/models/ai.models';

const aiTaskIds = [
  'upload',
  'research',
  'resume',
  'letter',
  'review',
  'answer',
  'completion',
  'scrape',
] as const;

export type AiTask = (typeof aiTaskIds)[number];

export type AiDefaultsSettings = Record<AiTask | 'default', string | null>;

// every key of AiDefaultsSettings, so normalize can loop over them without a cast
const settingKeys = ['default', ...aiTaskIds] as const;

export const aiTasks = [
  {
    id: 'upload',
    label: 'Resume imports',
    icon: 'pi-upload',
    group: 'Documents',
  },
  {
    id: 'research',
    label: 'Company & role research',
    icon: 'pi-search',
    group: 'Documents',
  },
  {
    id: 'resume',
    label: 'Resume writing',
    icon: 'pi-file',
    group: 'Documents',
  },
  {
    id: 'letter',
    label: 'Cover letters',
    icon: 'pi-envelope',
    group: 'Documents',
  },
  {
    id: 'review',
    label: 'Independent reviews',
    icon: 'pi-verified',
    group: 'Documents',
  },
  {
    id: 'answer',
    label: 'Application answers',
    icon: 'pi-comment',
    group: 'Writing assistance',
  },
  {
    id: 'completion',
    label: 'Writing suggestions',
    icon: 'pi-pencil',
    group: 'Writing assistance',
  },
  {
    id: 'scrape',
    label: 'Job enrichment',
    icon: 'pi-microchip-ai',
    group: 'Job discovery',
  },
] as const satisfies readonly {
  id: AiTask;
  label: string;
  icon: string;
  group: string;
}[];

export const recommendedModels: Partial<Record<AiTask, string>> = { resume: 'gpt-6-luna' };

const taskEfforts: Record<AiTask, ReasoningEffort | null> = {
  upload: 'low',
  research: 'low',
  resume: 'medium',
  letter: 'medium',
  review: 'medium',
  answer: 'medium',
  completion: null,
  scrape: null,
};

const storageKey = 'intern-radar.ai-defaults.v1';

export function emptySettings(): AiDefaultsSettings {
  return {
    default: null,
    upload: null,
    research: null,
    resume: null,
    letter: null,
    review: null,
    answer: null,
    completion: null,
    scrape: null,
  };
}

function normalize(value: unknown): AiDefaultsSettings {
  if (typeof value !== 'object' || value === null) {
    throw new Error('Invalid AI model defaults.');
  }
  const result = emptySettings();
  for (const key of settingKeys) {
    const model: unknown = Reflect.get(value, key);
    if (model == null || model === '') {
      continue;
    }
    if (typeof model !== 'string' || !model.trim() || model.trim().length > 200) {
      throw new Error('Model IDs must contain 1 to 200 characters.');
    }
    result[key] = model.trim();
  }
  return result;
}

@Injectable({ providedIn: 'root' })
export class AiDefaults {
  private readonly browser = inject(DOCUMENT).defaultView;
  private readonly saved = signal(this.load());
  readonly settings = this.saved.asReadonly();

  options(task: AiTask): AiModelOptions {
    const model = this.saved()[task] ?? recommendedModels[task] ?? this.saved().default;
    const effort = taskEfforts[task];
    return {
      ...(model ? { model } : {}),
      ...(effort ? { reasoning_effort: effort } : {}),
    };
  }

  resolve(task: AiTask, overrides: AiModelOptions = {}): AiModelOptions {
    return { ...this.options(task), ...overrides };
  }

  save(settings: AiDefaultsSettings): void {
    const normalized = normalize(settings);
    try {
      if (!this.browser) {
        throw new Error('Storage unavailable');
      }
      this.browser.localStorage.setItem(storageKey, JSON.stringify(normalized));
    } catch {
      throw new Error('Could not save model defaults. Allow browser storage and try again.');
    }
    this.saved.set(normalized);
  }

  private load(): AiDefaultsSettings {
    try {
      return normalize(JSON.parse(this.browser?.localStorage.getItem(storageKey) ?? 'null'));
    } catch {
      return emptySettings();
    }
  }
}
