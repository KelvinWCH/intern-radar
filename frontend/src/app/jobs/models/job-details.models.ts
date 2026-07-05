import * as validation from '../../shared/api-validation';
import type { educationListFields, requirementListFields } from '../constants/job-fields.constants';
type RequirementList = (typeof requirementListFields)[number][0];
type EducationList = (typeof educationListFields)[number][0];
export interface Education {
  degree_levels: string[];
  fields_of_study: string[];
  eligible_years_of_study: number[];
  graduation_years: number[];
  year_of_study_required: number | null;
  currently_enrolled: boolean | null;
  must_return_to_study: boolean | null;
  minimum_gpa: number | null;
  gpa_scale: number | null;
}
export type Qualifications = Record<RequirementList, string[]> & {
  education: Education;
  minimum_experience_years: number | null;
  work_authorization: string | null;
  visa_sponsorship_available: boolean | null;
  security_clearance: string | null;
};
export interface JobDetails {
  company: string;
  title: string;
  source_job_id: string | null;
  application_url: string | null;
  apply_url: string | null;
  company_url: string | null;
  locations: string[];
  terms: string[];
  category: string | null;
  sponsorship: string | null;
  active: boolean | null;
  date_posted: number | null;
  date_updated: number | null;
  summary: string | null;
  raw_description: string | null;
  cleaned_description?: string | null;
  qualifications: Qualifications | null;
}
export type JobEdit = Partial<JobDetails> & { version: number };

function nullableBoolean(value: unknown): boolean | null {
  return value === null || value === undefined ? null : validation.boolean(value);
}
function url(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = new URL(validation.text(value));
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('Invalid job URL.');
  }
  return parsed.href;
}
function qualifications(value: unknown): Qualifications | null {
  if (value === null || value === undefined) {
    return null;
  }
  const row = validation.object(value);
  const education = validation.object(row['education']);
  return {
    required_skills: validation.list(row['required_skills'], validation.text),
    preferred_skills: validation.list(row['preferred_skills'], validation.text),
    tech_stack: validation.list(row['tech_stack'], validation.text),
    experience_requirements: validation.list(row['experience_requirements'], validation.text),
    certifications: validation.list(row['certifications'], validation.text),
    languages: validation.list(row['languages'], validation.text),
    other_requirements: validation.list(row['other_requirements'], validation.text),
    minimum_experience_years: validation.timestamp(row['minimum_experience_years']),
    work_authorization: validation.optionalText(row['work_authorization']),
    security_clearance: validation.optionalText(row['security_clearance']),
    visa_sponsorship_available: nullableBoolean(row['visa_sponsorship_available']),
    education: {
      degree_levels: validation.list(education['degree_levels'], validation.text),
      fields_of_study: validation.list(education['fields_of_study'], validation.text),
      eligible_years_of_study: validation.list(
        education['eligible_years_of_study'],
        validation.number,
      ),
      graduation_years: validation.list(education['graduation_years'], validation.number),
      year_of_study_required: validation.timestamp(education['year_of_study_required']),
      currently_enrolled: nullableBoolean(education['currently_enrolled']),
      must_return_to_study: nullableBoolean(education['must_return_to_study']),
      minimum_gpa: validation.timestamp(education['minimum_gpa']),
      gpa_scale: validation.timestamp(education['gpa_scale']),
    },
  };
}

export function parseJobDetails(value: unknown): JobDetails {
  const row = validation.object(value);
  return {
    company: validation.text(row['company']),
    title: validation.text(row['title']),
    source_job_id: validation.optionalText(row['source_job_id'] ?? null),
    application_url: url(row['application_url']),
    apply_url: url(row['apply_url']),
    company_url: url(row['company_url']),
    locations: validation.list(row['locations'], validation.text),
    terms: validation.list(row['terms'], validation.text),
    category: validation.optionalText(row['category']),
    sponsorship: validation.optionalText(row['sponsorship'] ?? null),
    active: nullableBoolean(row['active']),
    date_posted: validation.timestamp(row['date_posted'] ?? null),
    date_updated: validation.timestamp(row['date_updated'] ?? null),
    summary: validation.optionalText(row['summary']),
    raw_description: validation.optionalText(row['raw_description']),
    cleaned_description: validation.optionalText(row['cleaned_description'] ?? null),
    qualifications: qualifications(row['qualifications']),
  };
}

export interface JobDraft {
  cleaned_description: string;
  company: string;
  title: string;
  application_url: string;
  raw_description: string;
  source_job_id: string;
  apply_url: string;
  company_url: string;
  locations: string;
  terms: string;
  category: string;
  sponsorship: string;
  active: boolean | null;
  date_posted: string;
  date_updated: string;
  summary: string;
  hasQualifications: boolean;
  requirements: Record<RequirementList, string>;
  education: Record<EducationList, string>;
  minimum_experience_years: number | null;
  year_of_study_required: number | null;
  minimum_gpa: number | null;
  gpa_scale: number | null;
  work_authorization: string;
  security_clearance: string;
  visa_sponsorship_available: boolean | null;
  currently_enrolled: boolean | null;
  must_return_to_study: boolean | null;
}
function date(value: number | null | undefined): string {
  return value === null || value === undefined
    ? ''
    : new Date(value * 1000).toISOString().slice(0, 10);
}
export function jobDraft(details?: JobDetails): JobDraft {
  const qualifications = details?.qualifications;
  const education = qualifications?.education;
  return {
    company: details?.company ?? '',
    title: details?.title ?? '',
    application_url: details?.application_url ?? '',
    raw_description: details?.raw_description ?? '',
    cleaned_description: details?.cleaned_description ?? '',
    source_job_id: details?.source_job_id ?? '',
    apply_url: details?.apply_url ?? '',
    company_url: details?.company_url ?? '',
    locations: details?.locations.join('\n') ?? '',
    terms: details?.terms.join('\n') ?? '',
    category: details?.category ?? '',
    sponsorship: details?.sponsorship ?? '',
    active: details ? details.active : true,
    date_posted: date(details?.date_posted),
    date_updated: date(details?.date_updated),
    summary: details?.summary ?? '',
    hasQualifications: !!qualifications,
    requirements: {
      required_skills: qualifications?.required_skills.join('\n') ?? '',
      preferred_skills: qualifications?.preferred_skills.join('\n') ?? '',
      tech_stack: qualifications?.tech_stack.join('\n') ?? '',
      experience_requirements: qualifications?.experience_requirements.join('\n') ?? '',
      certifications: qualifications?.certifications.join('\n') ?? '',
      languages: qualifications?.languages.join('\n') ?? '',
      other_requirements: qualifications?.other_requirements.join('\n') ?? '',
    },
    education: {
      degree_levels: education?.degree_levels.join('\n') ?? '',
      fields_of_study: education?.fields_of_study.join('\n') ?? '',
      eligible_years_of_study: education?.eligible_years_of_study.join('\n') ?? '',
      graduation_years: education?.graduation_years.join('\n') ?? '',
    },
    minimum_experience_years: qualifications?.minimum_experience_years ?? null,
    year_of_study_required: education?.year_of_study_required ?? null,
    minimum_gpa: education?.minimum_gpa ?? null,
    gpa_scale: education?.gpa_scale ?? null,
    work_authorization: qualifications?.work_authorization ?? '',
    security_clearance: qualifications?.security_clearance ?? '',
    visa_sponsorship_available: qualifications?.visa_sponsorship_available ?? null,
    currently_enrolled: education?.currently_enrolled ?? null,
    must_return_to_study: education?.must_return_to_study ?? null,
  };
}
function lines(value: string): string[] {
  return [
    ...new Set(
      value
        .split('\n')
        .map((line): string => line.trim())
        .filter(Boolean),
    ),
  ];
}
function years(value: string, minimum: number, maximum: number): number[] {
  return lines(value).map((line): number => {
    const year = Number(line);
    if (!Number.isSafeInteger(year) || year < minimum || year > maximum) {
      throw new Error('Enter valid years, one per line.');
    }
    return year;
  });
}
function timestamp(value: string): number | null {
  if (!value) {
    return null;
  }
  const result = Date.parse(`${value}T00:00:00Z`) / 1000;
  if (!Number.isSafeInteger(result) || result < 0) {
    throw new Error('Enter a valid date from 1970 onward.');
  }
  return result;
}
export function draftDetails(draft: JobDraft): JobDetails {
  return {
    company: draft.company.trim() || 'Not specified',
    title: draft.title.trim() || 'Not specified',
    application_url: url(draft.application_url.trim() || null),
    raw_description: draft.raw_description.trim() || null,
    cleaned_description: draft.cleaned_description.trim() || null,
    source_job_id: draft.source_job_id.trim() || null,
    apply_url: url(draft.apply_url.trim() || null),
    company_url: url(draft.company_url.trim() || null),
    locations: lines(draft.locations),
    terms: lines(draft.terms),
    category: draft.category.trim() || null,
    sponsorship: draft.sponsorship.trim() || null,
    active: draft.active,
    date_posted: timestamp(draft.date_posted),
    date_updated: timestamp(draft.date_updated),
    summary: draft.summary.trim() || null,
    qualifications: draft.hasQualifications
      ? {
          required_skills: lines(draft.requirements.required_skills),
          preferred_skills: lines(draft.requirements.preferred_skills),
          tech_stack: lines(draft.requirements.tech_stack),
          experience_requirements: lines(draft.requirements.experience_requirements),
          certifications: lines(draft.requirements.certifications),
          languages: lines(draft.requirements.languages),
          other_requirements: lines(draft.requirements.other_requirements),
          minimum_experience_years: draft.minimum_experience_years,
          work_authorization: draft.work_authorization.trim() || null,
          security_clearance: draft.security_clearance.trim() || null,
          visa_sponsorship_available: draft.visa_sponsorship_available,
          education: {
            degree_levels: lines(draft.education.degree_levels),
            fields_of_study: lines(draft.education.fields_of_study),
            eligible_years_of_study: years(draft.education.eligible_years_of_study, 1, 100),
            graduation_years: years(draft.education.graduation_years, 1900, 2200),
            year_of_study_required: draft.year_of_study_required,
            currently_enrolled: draft.currently_enrolled,
            must_return_to_study: draft.must_return_to_study,
            minimum_gpa: draft.minimum_gpa,
            gpa_scale: draft.gpa_scale,
          },
        }
      : null,
  };
}

export function changedDetails(current: JobDetails, original: JobDetails): Partial<JobDetails> {
  return changedFields(current, original);
}

// for...in over a type parameter keeps the keys typed, so no cast is needed
function changedFields<T extends object>(current: T, original: T): Partial<T> {
  const changes: Partial<T> = {};
  for (const key in current) {
    if (JSON.stringify(current[key]) !== JSON.stringify(original[key])) {
      changes[key] = current[key];
    }
  }
  return changes;
}
