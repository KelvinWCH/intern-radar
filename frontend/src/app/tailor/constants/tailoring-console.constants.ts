import type { TailoringEvent } from '../models/document.models';

export const tailoringStepIcons: Record<TailoringEvent['stage'], string> = {
  queued: 'pi-clock',
  prepare: 'pi-cog',
  ai: 'pi-microchip-ai',
  output: 'pi-file',
  validate: 'pi-check-circle',
  compile: 'pi-file-pdf',
  retry: 'pi-refresh',
  save: 'pi-save',
  done: 'pi-flag',
  error: 'pi-times-circle',
  paused: 'pi-pause-circle',
  resumed: 'pi-play-circle',
  cancelled: 'pi-ban',
};

export const tailoringStepTones: Record<TailoringEvent['stage'], string> = {
  queued: 'muted',
  prepare: 'muted',
  ai: 'ai',
  output: 'ai',
  validate: 'good',
  compile: 'muted',
  retry: 'warn',
  save: 'good',
  done: 'good',
  error: 'bad',
  paused: 'warn',
  resumed: 'ai',
  cancelled: 'muted',
};
