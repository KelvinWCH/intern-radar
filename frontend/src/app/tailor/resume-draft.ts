import { isRecord } from '../shared/api-validation';
import type { DocumentDetail } from './models/document.models';
import type {
  BulletLayout,
  DraftPreview,
  EducationDraft,
  ExperienceDraft,
  FittedLine,
  ProjectDraft,
  ResumeDraft,
  SectionDraft,
  SkillDraft,
} from './models/resume-editor.models';
import type { GeneratedResume, RequirementMatch } from './models/resume.models';

export function canEditResume(
  document: Pick<DocumentDetail, 'status' | 'resume' | 'unfitted_resume'>,
): boolean {
  return (
    ['completed', 'failed', 'cancelled'].includes(document.status) &&
    !!(document.resume ?? document.unfitted_resume)
  );
}

export function savedResume(
  document: Pick<DocumentDetail, 'resume' | 'unfitted_resume'>,
): GeneratedResume | null {
  return document.resume ?? document.unfitted_resume?.document ?? null;
}

export function splitList(text: string): string[] {
  return text
    .split(',')
    .map((item): string => item.trim())
    .filter(Boolean);
}

export function resumeDraft(resume: GeneratedResume): ResumeDraft {
  return {
    header: {
      name: resume.name,
      email: resume.email ?? '',
      phone: resume.phone ?? '',
      location: resume.location ?? '',
      linkedin: resume.linkedin ?? '',
      linkedinLabel: resume.linkedin_label ?? '',
      github: resume.github ?? '',
      links: [...resume.links],
    },
    education: resume.education.map((entry): EducationDraft => ({
      institution: entry.institution,
      degree: entry.degree ?? '',
      fieldOfStudy: entry.field_of_study ?? '',
      location: entry.location ?? '',
      startDate: entry.start_date ?? '',
      endDate: entry.end_date ?? '',
      coursework: entry.coursework.join(', '),
      bullets: [...entry.bullets],
    })),
    experience: resume.experience.map((entry): ExperienceDraft => ({
      loadedAs: entry.title,
      title: entry.title,
      company: entry.company,
      location: entry.location ?? '',
      startDate: entry.start_date ?? '',
      endDate: entry.end_date ?? '',
      bullets: [...entry.bullets],
    })),
    projects: resume.projects.map((entry): ProjectDraft => ({
      loadedAs: entry.name,
      name: entry.name,
      url: entry.url ?? '',
      technologies: entry.technologies.join(', '),
      startDate: entry.start_date ?? '',
      endDate: entry.end_date ?? '',
      bullets: [...entry.bullets],
    })),
    skills: resume.skills.map((group): SkillDraft => ({
      category: group.category,
      items: group.items.join(', '),
    })),
    additionalSections: resume.additional_sections.map((section): SectionDraft => ({
      title: section.title,
      items: [...section.items],
    })),
  };
}

export function newEducation(): EducationDraft {
  return {
    institution: '',
    degree: '',
    fieldOfStudy: '',
    location: '',
    startDate: '',
    endDate: '',
    coursework: '',
    bullets: [],
  };
}

export function newExperience(): ExperienceDraft {
  return {
    loadedAs: null,
    title: '',
    company: '',
    location: '',
    startDate: '',
    endDate: '',
    bullets: [''],
  };
}

export function newProject(): ProjectDraft {
  return {
    loadedAs: null,
    name: '',
    url: '',
    technologies: '',
    startDate: '',
    endDate: '',
    bullets: [''],
  };
}

export function draftIssues(draft: ResumeDraft): string[] {
  const issues: string[] = [];
  const blank = (text: string): boolean => !text.trim();
  if (blank(draft.header.name)) {
    issues.push('Add your name.');
  }
  draft.education.forEach((entry, index): void => {
    if (blank(entry.institution)) {
      issues.push(`Education ${String(index + 1)} needs a school.`);
    }
  });
  draft.experience.forEach((entry, index): void => {
    const position = `Experience ${String(index + 1)}`;
    if (blank(entry.title)) {
      issues.push(`${position} needs a job title.`);
    }
    if (blank(entry.company)) {
      issues.push(`${position} needs a company.`);
    }
  });
  draft.projects.forEach((entry, index): void => {
    if (blank(entry.name)) {
      issues.push(`Project ${String(index + 1)} needs a name.`);
    }
  });
  draft.skills.forEach((group, index): void => {
    if (blank(group.category) && splitList(group.items).length) {
      issues.push(`Skill group ${String(index + 1)} needs a category.`);
    }
  });
  draft.additionalSections.forEach((section, index): void => {
    if (blank(section.title) && section.items.some((item): boolean => !blank(item))) {
      issues.push(`Section ${String(index + 1)} needs a title.`);
    }
  });
  return issues;
}

export function draftResume(draft: ResumeDraft, base: GeneratedResume): GeneratedResume {
  const optional = (text: string): string | null => text.trim() || null;
  const lines = (items: readonly string[]): string[] =>
    items.map((item): string => item.trim()).filter(Boolean);
  const named = [
    ...draft.experience.map((entry) => ({ loadedAs: entry.loadedAs, name: entry.title.trim() })),
    ...draft.projects.map((entry) => ({ loadedAs: entry.loadedAs, name: entry.name.trim() })),
  ];
  return {
    ...(base.requirement_coverage
      ? { requirement_coverage: followNames(base, named, base.requirement_coverage) }
      : {}),
    name: draft.header.name.trim(),
    email: optional(draft.header.email),
    phone: optional(draft.header.phone),
    location: optional(draft.header.location),
    linkedin: optional(draft.header.linkedin),
    linkedin_label: optional(draft.header.linkedinLabel),
    github: optional(draft.header.github),
    links: lines(draft.header.links),
    education: draft.education.map((entry) => ({
      institution: entry.institution.trim(),
      degree: optional(entry.degree),
      field_of_study: optional(entry.fieldOfStudy),
      location: optional(entry.location),
      start_date: optional(entry.startDate),
      end_date: optional(entry.endDate),
      bullets: lines(entry.bullets),
      coursework: splitList(entry.coursework),
    })),
    experience: draft.experience.map((entry) => ({
      company: entry.company.trim(),
      title: entry.title.trim(),
      location: optional(entry.location),
      start_date: optional(entry.startDate),
      end_date: optional(entry.endDate),
      bullets: lines(entry.bullets),
    })),
    projects: draft.projects.map((entry) => ({
      name: entry.name.trim(),
      url: optional(entry.url),
      technologies: splitList(entry.technologies),
      start_date: optional(entry.startDate),
      end_date: optional(entry.endDate),
      bullets: lines(entry.bullets),
    })),
    skills: draft.skills
      .map((group) => ({ category: group.category.trim(), items: splitList(group.items) }))
      .filter((group): boolean => group.items.length > 0),
    additional_sections: draft.additionalSections
      .map((section) => ({ title: section.title.trim(), items: lines(section.items) }))
      .filter((section): boolean => section.items.length > 0),
  };
}

function followNames(
  base: GeneratedResume,
  named: readonly { readonly loadedAs: string | null; readonly name: string }[],
  coverage: readonly RequirementMatch[],
): RequirementMatch[] {
  const loaded = new Set([
    ...base.experience.map((entry): string => entry.title),
    ...base.projects.map((entry): string => entry.name),
  ]);
  const current = new Map<string, Set<string>>();
  for (const { loadedAs, name } of named) {
    if (loadedAs === null) {
      continue;
    }
    current.set(loadedAs, (current.get(loadedAs) ?? new Set<string>()).add(name));
  }
  const rename = (entry: string): string[] => {
    if (!loaded.has(entry)) {
      return [entry];
    }
    const names = [...(current.get(entry) ?? [])];
    return names.length > 1 ? [entry] : names;
  };
  return coverage.map((match): RequirementMatch => ({
    ...match,
    entries: [...new Set(match.entries.flatMap(rename))],
  }));
}

export function resumeKey(resume: GeneratedResume): string {
  const canonical = (value: unknown): unknown => {
    if (Array.isArray(value)) {
      return value.map(canonical);
    }
    if (!isRecord(value)) {
      return value;
    }
    const entries = Object.entries(value)
      .filter(([key, item]): boolean => key !== 'ai_usage' && item !== undefined)
      .sort(([left], [right]): number => left.localeCompare(right));
    return Object.fromEntries(
      entries.map(([key, item]): [string, unknown] => [key, canonical(item)]),
    );
  };
  return JSON.stringify(canonical(resume));
}

export function layoutKey(section: 'experience' | 'projects', entry: number, text: string): string {
  return JSON.stringify([section, entry, text.trim()]);
}

export function bulletLayouts(
  resume: GeneratedResume,
  preview: DraftPreview,
): ReadonlyMap<string, BulletLayout> {
  const layouts = new Map<string, BulletLayout>();
  for (const layout of preview.bullets) {
    const entries = layout.section === 'experience' ? resume.experience : resume.projects;
    const text = entries[layout.entry]?.bullets[layout.bullet];
    if (text !== undefined) {
      layouts.set(layoutKey(layout.section, layout.entry, text), layout);
    }
  }
  return layouts;
}

export function fittedKey(
  section: 'projects' | 'education',
  entry: number,
  items: readonly string[],
): string {
  return JSON.stringify([section, entry, items]);
}

export function fittedLines(
  resume: GeneratedResume,
  preview: DraftPreview,
): ReadonlyMap<string, FittedLine> {
  const lines = new Map<string, FittedLine>();
  for (const line of preview.fitted) {
    const items =
      line.section === 'projects'
        ? resume.projects[line.entry]?.technologies
        : resume.education[line.entry]?.coursework;
    if (items) {
      lines.set(fittedKey(line.section, line.entry, items), line);
    }
  }
  return lines;
}
