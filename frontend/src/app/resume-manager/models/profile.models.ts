import * as validation from '../../shared/api-validation';
import type { ExperienceContext } from './experience-context.models';
import { parseExperienceContext } from './experience-context.models';
import type {
  GeneratedResume,
  ResumeEducation,
  ResumeExperience,
  ResumeProject,
  ResumeSection,
  ResumeSkill,
} from '../../tailor/models/resume.models';
import { parseGeneratedResume } from '../../tailor/models/resume.models';
export interface SwitchableEntry {
  readonly enabled?: boolean;
}
export interface SourceExperience extends ResumeExperience, SwitchableEntry {
  readonly raw_description: string;
  readonly context?: ExperienceContext;
  readonly bullet_context?: readonly (string | null)[];
}
export interface SourceProject extends ResumeProject, SwitchableEntry {
  readonly available_technologies?: readonly string[];
  readonly raw_description: string;
  readonly context?: ExperienceContext;
  readonly bullet_context?: readonly (string | null)[];
}
export interface SourceEducation extends ResumeEducation, SwitchableEntry {
  readonly available_coursework?: readonly string[];
}
export interface SourceSkill extends ResumeSkill, SwitchableEntry {
  readonly available_items?: readonly string[];
}
export interface SourceSection extends ResumeSection, SwitchableEntry {}
export interface UserResume extends Omit<GeneratedResume, 'ai_usage'> {
  readonly education: readonly SourceEducation[];
  readonly skills: readonly SourceSkill[];
  readonly experience: readonly SourceExperience[];
  readonly projects: readonly SourceProject[];
  readonly additional_sections: readonly SourceSection[];
}
export interface ProfileState {
  readonly resume: UserResume | null;
  readonly revision: number;
  readonly updated_at: number | null;
}
function bulletNotes(value: unknown, count: number): (string | null)[] {
  const notes =
    value === undefined || value === null
      ? []
      : validation.list(value, (item): string | null =>
          item === null ? null : validation.text(item),
        );
  return Array.from({ length: count }, (_item, index): string | null => notes[index] ?? null);
}
function entrySwitch(value: unknown): SwitchableEntry {
  return value == null || validation.boolean(value) ? {} : { enabled: false };
}
export function parseUserResume(value: unknown): UserResume {
  const row = validation.object(value);
  const base = parseGeneratedResume(row);
  const experience = validation.list(row['experience'], validation.object);
  const projects = validation.list(row['projects'], validation.object);
  const skills = validation.list(row['skills'], validation.object);
  const education = validation.list(row['education'], validation.object);
  const sections = validation.list(row['additional_sections'], validation.object);
  return {
    name: base.name,
    email: base.email,
    phone: base.phone,
    location: base.location,
    linkedin: base.linkedin ?? null,
    linkedin_label: base.linkedin_label ?? null,
    github: base.github ?? null,
    links: base.links,
    education: base.education.map((entry, index): SourceEducation => ({
      ...entry,
      ...entrySwitch(education[index]?.['enabled']),
      available_coursework:
        education[index]?.['available_coursework'] === undefined
          ? [...entry.coursework]
          : validation.list(education[index]['available_coursework'], validation.text),
    })),
    skills: base.skills.map((entry, index): SourceSkill => ({
      ...entry,
      ...entrySwitch(skills[index]?.['enabled']),
      available_items:
        skills[index]?.['available_items'] === undefined
          ? [...entry.items]
          : validation.list(skills[index]['available_items'], validation.text),
    })),
    additional_sections: base.additional_sections.map((entry, index): SourceSection => ({
      ...entry,
      ...entrySwitch(sections[index]?.['enabled']),
    })),
    experience: base.experience.map((entry, index): SourceExperience => ({
      ...entry,
      ...entrySwitch(experience[index]?.['enabled']),
      raw_description: validation.text(experience[index]?.['raw_description']),
      context: parseExperienceContext(experience[index]?.['context']),
      bullet_context: bulletNotes(experience[index]?.['bullet_context'], entry.bullets.length),
    })),
    projects: base.projects.map((entry, index): SourceProject => ({
      ...entry,
      ...entrySwitch(projects[index]?.['enabled']),
      available_technologies:
        projects[index]?.['available_technologies'] === undefined
          ? [...entry.technologies]
          : validation.list(projects[index]['available_technologies'], validation.text),
      raw_description: validation.text(projects[index]?.['raw_description']),
      context: parseExperienceContext(projects[index]?.['context']),
      bullet_context: bulletNotes(projects[index]?.['bullet_context'], entry.bullets.length),
    })),
  };
}
export function parseProfile(value: unknown): ProfileState {
  const row = validation.object(value);
  return {
    resume: row['resume'] === null ? null : parseUserResume(row['resume']),
    revision: validation.number(row['revision']),
    updated_at: validation.timestamp(row['updated_at']),
  };
}
