import type { OutputKind, OutputTag } from '../models/ai-output.models';

export const outputKinds: Readonly<Record<string, OutputKind>> = {
  company_role_source_plan: { title: 'Company site lookup', icon: 'pi-globe' },
  company_role_research: { title: 'Research brief', icon: 'pi-search' },
  tailored_resume_content: { title: 'Resume draft', icon: 'pi-file' },
  cover_letter_content: { title: 'Cover letter draft', icon: 'pi-envelope' },
  application_review: { title: 'Independent review', icon: 'pi-verified' },
};

export const outputKindsByStep: Readonly<Record<string, OutputKind>> = {
  Research: { title: 'Research', icon: 'pi-search' },
  Resume: { title: 'Resume draft', icon: 'pi-file' },
  'Cover Letter': { title: 'Cover letter draft', icon: 'pi-envelope' },
  Reviewer: { title: 'Independent review', icon: 'pi-verified' },
};

export const defaultOutputKind: OutputKind = { title: 'AI output', icon: 'pi-sparkles' };

export const importanceTags: Readonly<Record<string, OutputTag>> = {
  required: { label: 'Required', tone: 'accent' },
  preferred: { label: 'Preferred', tone: 'neutral' },
};

export const gapTags: Readonly<Record<string, OutputTag>> = {
  not_shown: { label: 'Supported, not shown', tone: 'warn' },
  no_evidence: { label: 'Not in your profile', tone: 'bad' },
};

export const severityTags: Readonly<Record<string, OutputTag>> = {
  error: { label: 'Error', tone: 'bad' },
  warning: { label: 'Warning', tone: 'warn' },
  suggestion: { label: 'Suggestion', tone: 'neutral' },
};
