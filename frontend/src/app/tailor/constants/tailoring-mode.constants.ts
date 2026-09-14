import type { AiModelOptions } from '../../shared/models/ai.models';
import type { TailoringMode } from '../models/document.models';

export const oneShotDefaults: AiModelOptions = {};

const modeStorageKey = 'intern-radar.tailoring-mode.v1';

export function loadTailoringMode(): TailoringMode {
  try {
    return localStorage.getItem(modeStorageKey) === 'one_shot' ? 'one_shot' : 'staged';
  } catch {
    return 'staged';
  }
}

export function saveTailoringMode(mode: TailoringMode): void {
  try {
    localStorage.setItem(modeStorageKey, mode);
  } catch {
    // storage blocked, the choice still works for this visit
  }
}
