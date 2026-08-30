import type { ActivityKind } from '../models/activity.models';

export const activityKindLabels: Record<ActivityKind, string> = {
  job_added: 'Added a job',
  job_saved: 'Saved a job',
  application_updated: 'Updated application',
  application_marked: 'Marked as applied',
  documents_generated: 'Tailored documents',
  resume_updated: 'Updated source resume',
};

export const activityRangeDays = [7, 30, 90];
