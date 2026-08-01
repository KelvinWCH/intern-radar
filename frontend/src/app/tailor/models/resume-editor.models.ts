import type { ProfileHeader } from '../../resume-manager/models/editor.models';
import * as validation from '../../shared/api-validation';
import type { GeneratedResume } from './resume.models';

export interface EducationDraft {
  institution: string;
  degree: string;
  fieldOfStudy: string;
  location: string;
  startDate: string;
  endDate: string;
  coursework: string;
  bullets: string[];
}

export interface ExperienceDraft {
  readonly loadedAs: string | null;
  title: string;
  company: string;
  location: string;
  startDate: string;
  endDate: string;
  bullets: string[];
}

export interface ProjectDraft {
  readonly loadedAs: string | null;
  name: string;
  url: string;
  technologies: string;
  startDate: string;
  endDate: string;
  bullets: string[];
}

export interface SkillDraft {
  category: string;
  items: string;
}

export interface SectionDraft {
  title: string;
  items: string[];
}

export interface ResumeDraft {
  header: ProfileHeader;
  education: EducationDraft[];
  experience: ExperienceDraft[];
  projects: ProjectDraft[];
  skills: SkillDraft[];
  additionalSections: SectionDraft[];
}

export type BulletIssue = 'wrapped' | 'dangling' | 'late' | 'short';

export interface BulletLayout {
  readonly section: 'experience' | 'projects';
  readonly entry: number;
  readonly bullet: number;
  readonly lines: number;
  readonly issue: BulletIssue | null;
  readonly characters: number;
}

export interface FittedLine {
  readonly section: 'projects' | 'education';
  readonly entry: number;
  readonly printed: number;
}

export interface DraftPreview {
  readonly pdf: Blob;
  readonly page_count: number;
  readonly overflow_lines: number;
  readonly blank_inches: number;
  readonly bullets: readonly BulletLayout[];
  readonly fitted: readonly FittedLine[];
}

export interface ShownPreview {
  readonly resume: GeneratedResume;
  readonly key: string;
  readonly preview: DraftPreview;
  readonly url: string;
}

const MAX_PREVIEW_BYTES = 2_500_000;

export function parseDraftPreview(value: unknown): DraftPreview {
  const row = validation.object(value);
  const binary = atob(validation.text(row['pdf_base64']));
  if (binary.length > MAX_PREVIEW_BYTES || !binary.startsWith('%PDF-')) {
    throw new Error('Invalid preview PDF.');
  }
  const bytes = Uint8Array.from(binary, (character): number => character.charCodeAt(0));
  const pageCount = count(row['page_count']);
  if (pageCount < 1) {
    throw new Error('Invalid preview page count.');
  }
  return {
    pdf: new Blob([bytes], { type: 'application/pdf' }),
    page_count: pageCount,
    overflow_lines: count(row['overflow_lines']),
    blank_inches: validation.number(row['blank_inches']),
    bullets: validation.list(row['bullets'], parseBulletLayout),
    fitted: validation.list(row['fitted'], (item): FittedLine => {
      const line = validation.object(item);
      const section = line['section'];
      if (section !== 'projects' && section !== 'education') {
        throw new Error('Invalid fitted line.');
      }
      return { section, entry: count(line['entry']), printed: count(line['printed']) };
    }),
  };
}

function parseBulletLayout(value: unknown): BulletLayout {
  const row = validation.object(value);
  const section = row['section'];
  if (section !== 'experience' && section !== 'projects') {
    throw new Error('Invalid bullet.');
  }
  const issue = row['issue'] ?? null;
  if (
    issue !== null &&
    issue !== 'wrapped' &&
    issue !== 'dangling' &&
    issue !== 'late' &&
    issue !== 'short'
  ) {
    throw new Error('Invalid bullet issue.');
  }
  return {
    section,
    entry: count(row['entry']),
    bullet: count(row['bullet']),
    lines: count(row['lines']),
    issue,
    characters: count(row['characters'] ?? 0),
  };
}

function count(value: unknown): number {
  const result = validation.number(value);
  if (!Number.isInteger(result)) {
    throw new Error('Invalid API count.');
  }
  return result;
}
