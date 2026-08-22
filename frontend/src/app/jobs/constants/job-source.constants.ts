import type { SourceType } from '../models/job.models';

export const jobSourceLabels: Record<SourceType, string> = {
  scraped: 'Scraped',
  user_added: 'User added',
  user_auto_add: 'User auto add',
};
