import type { ResumeSettings } from '../models/user-profile.models';

export const defaultResumeSettings: ResumeSettings = {
  min_experience_bullets: 3,
  min_project_bullets: 2,
};
export const resumeSettingFields = [
  { key: 'min_experience_bullets', label: 'Experience entries', min: 1, max: 6 },
  { key: 'min_project_bullets', label: 'Projects', min: 1, max: 6 },
] as const;
