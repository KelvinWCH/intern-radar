import type { CanDeactivateFn } from '@angular/router';
import type { ResumeEditor } from './resume-editor';

export const confirmLeavingResumeEditor: CanDeactivateFn<ResumeEditor> = (editor): boolean =>
  editor.canLeave();
