import type { JobInput } from '../../jobs/models/job.models';
import type { AiUsage } from '../../shared/models/ai.models';
import { parseAiUsage } from '../../shared/models/ai.models';
import { isRecord } from '../../shared/api-validation';

export interface ResumeProfile {
  readonly name: string;
}

export interface ResumeEducation {
  readonly institution: string;
  readonly degree: string | null;
  readonly field_of_study: string | null;
  readonly location: string | null;
  readonly start_date: string | null;
  readonly end_date: string | null;
  readonly bullets: readonly string[];
  readonly coursework: readonly string[];
}

export interface ResumeExperience {
  readonly company: string;
  readonly title: string;
  readonly location: string | null;
  readonly start_date: string | null;
  readonly end_date: string | null;
  readonly bullets: readonly string[];
}

export interface ResumeProject {
  readonly name: string;
  readonly url: string | null;
  readonly technologies: readonly string[];
  readonly start_date: string | null;
  readonly end_date: string | null;
  readonly bullets: readonly string[];
}

export interface ResumeSkill {
  readonly category: string;
  readonly items: readonly string[];
}

export interface ResumeSection {
  readonly title: string;
  readonly items: readonly string[];
}

export interface RequirementMatch {
  readonly requirement: string;
  readonly importance: 'required' | 'preferred';
  readonly entries: readonly string[];
}

export interface GeneratedResume {
  readonly ai_usage?: AiUsage | null;
  readonly requirement_coverage?: readonly RequirementMatch[];
  readonly name: string;
  readonly email: string | null;
  readonly phone: string | null;
  readonly location: string | null;
  readonly linkedin?: string | null;
  readonly linkedin_label?: string | null;
  readonly github?: string | null;
  readonly links: readonly string[];
  readonly education: readonly ResumeEducation[];
  readonly experience: readonly ResumeExperience[];
  readonly projects: readonly ResumeProject[];
  readonly skills: readonly ResumeSkill[];
  readonly additional_sections: readonly ResumeSection[];
}

export type TailoringJob = JobInput;

function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error('Invalid resume response.');
  }
  return value;
}
function text(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error('Invalid resume text.');
  }
  return value;
}
function nullableText(value: unknown): string | null {
  if (value === null || typeof value === 'string') {
    return value;
  }
  throw new Error('Invalid optional resume text.');
}
function optionalText(value: unknown): string | null {
  return value === undefined ? null : nullableText(value);
}
function list<T>(value: unknown, parse: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) {
    throw new Error('Invalid resume list.');
  }
  return value.map((item: unknown): T => parse(item));
}
function dates(value: Record<string, unknown>): {
  start_date: string | null;
  end_date: string | null;
} {
  return {
    start_date: nullableText(value['start_date']),
    end_date: nullableText(value['end_date']),
  };
}

export function parseResumeProfile(value: unknown): ResumeProfile {
  return { name: text(record(value)['name']) };
}

export function parseGeneratedResume(value: unknown): GeneratedResume {
  const resume = record(value);
  return {
    ai_usage: parseAiUsage(resume['ai_usage']),
    ...(resume['requirement_coverage'] === undefined
      ? {}
      : {
          requirement_coverage: list(resume['requirement_coverage'], (item): RequirementMatch => {
            const match = record(item);
            const importance = text(match['importance']);
            if (importance !== 'required' && importance !== 'preferred') {
              throw new Error('Invalid requirement importance.');
            }
            return {
              requirement: text(match['requirement']),
              importance,
              entries: list(match['entries'], text),
            };
          }),
        }),
    name: text(resume['name']),
    email: nullableText(resume['email']),
    phone: nullableText(resume['phone']),
    location: nullableText(resume['location']),
    linkedin: optionalText(resume['linkedin']),
    linkedin_label: optionalText(resume['linkedin_label']),
    github: optionalText(resume['github']),
    links: list(resume['links'], text),
    education: list(resume['education'], (item): ResumeEducation => {
      const entry = record(item);
      return {
        institution: text(entry['institution']),
        degree: nullableText(entry['degree']),
        field_of_study: nullableText(entry['field_of_study']),
        location: nullableText(entry['location']),
        ...dates(entry),
        bullets: list(entry['bullets'], text),
        coursework: entry['coursework'] === undefined ? [] : list(entry['coursework'], text),
      };
    }),
    experience: list(resume['experience'], (item): ResumeExperience => {
      const entry = record(item);
      return {
        company: text(entry['company']),
        title: text(entry['title']),
        location: nullableText(entry['location']),
        ...dates(entry),
        bullets: list(entry['bullets'], text),
      };
    }),
    projects: list(resume['projects'], (item): ResumeProject => {
      const entry = record(item);
      return {
        name: text(entry['name']),
        url: nullableText(entry['url']),
        technologies: list(entry['technologies'], text),
        ...dates(entry),
        bullets: list(entry['bullets'], text),
      };
    }),
    skills: list(resume['skills'], (item): ResumeSkill => {
      const entry = record(item);
      return { category: text(entry['category']), items: list(entry['items'], text) };
    }),
    additional_sections: list(resume['additional_sections'], (item): ResumeSection => {
      const entry = record(item);
      return { title: text(entry['title']), items: list(entry['items'], text) };
    }),
  };
}

export function resumePayload(resume: GeneratedResume): Record<string, unknown> {
  const payload: Record<string, unknown> = { ...resume };
  delete payload['ai_usage'];
  return payload;
}

export function parseLatex(value: unknown): string {
  return text(record(value)['latex']);
}
