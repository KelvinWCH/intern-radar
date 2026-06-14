import * as validation from '../../shared/api-validation';
import type { UserResume } from './profile.models';
import { parseUserResume } from './profile.models';
import { defaultResumeSettings, resumeSettingFields } from '../constants/resume-settings.constants';

export interface CandidatePreferences {
  target_roles: string[];
  preferred_locations: string[];
  available_terms: string[];
  graduation_year: number | null;
  year_of_study: number | null;
  currently_enrolled: boolean | null;
  returning_to_study: boolean | null;
  requires_sponsorship: boolean | null;
  experience_years: number | null;
  gpa: number | null;
  gpa_scale: number | null;
  work_authorization: string | null;
}
export interface ResumeSettings {
  min_experience_bullets: number;
  min_project_bullets: number;
}
export interface CandidateStory {
  title: string;
  related_experience: string | null;
  situation: string | null;
  task: string | null;
  action: string;
  result: string | null;
  learning: string | null;
  skills: string[];
  evidence: string[];
}
export interface CandidateAnswer {
  question: string;
  answer: string;
  context: string | null;
}
export interface UserProfile extends UserResume {
  about: string | null;
  goals: string | null;
  stories: CandidateStory[];
  answers: CandidateAnswer[];
  preferences: CandidatePreferences;
  resume_settings: ResumeSettings;
}
export interface UserProfileState {
  profile: UserProfile | null;
  revision: number;
  updated_at: number | null;
}

export function parsePreferences(value: unknown): CandidatePreferences {
  const row = value == null ? {} : validation.object(value);
  return {
    target_roles: validation.list(row['target_roles'] ?? [], validation.text),
    preferred_locations: validation.list(row['preferred_locations'] ?? [], validation.text),
    available_terms: validation.list(row['available_terms'] ?? [], validation.text),
    graduation_year: validation.timestamp(row['graduation_year'] ?? null),
    year_of_study: validation.timestamp(row['year_of_study'] ?? null),
    experience_years: validation.timestamp(row['experience_years'] ?? null),
    gpa: validation.timestamp(row['gpa'] ?? null),
    gpa_scale: validation.timestamp(row['gpa_scale'] ?? null),
    currently_enrolled:
      row['currently_enrolled'] == null ? null : validation.boolean(row['currently_enrolled']),
    returning_to_study:
      row['returning_to_study'] == null ? null : validation.boolean(row['returning_to_study']),
    requires_sponsorship:
      row['requires_sponsorship'] == null ? null : validation.boolean(row['requires_sponsorship']),
    work_authorization: validation.optionalText(row['work_authorization'] ?? null),
  };
}
export function parseResumeSettings(value: unknown): ResumeSettings {
  const row = value == null ? {} : validation.object(value);
  return {
    min_experience_bullets: validation.number(
      row['min_experience_bullets'] ?? defaultResumeSettings.min_experience_bullets,
    ),
    min_project_bullets: validation.number(
      row['min_project_bullets'] ?? defaultResumeSettings.min_project_bullets,
    ),
  };
}
export function boundedResumeSettings(value: ResumeSettings): ResumeSettings {
  const bounded = { ...defaultResumeSettings };
  for (const field of resumeSettingFields) {
    const count: unknown = value[field.key];
    if (typeof count === 'number' && Number.isFinite(count)) {
      bounded[field.key] = Math.min(field.max, Math.max(field.min, Math.round(count)));
    }
  }
  return bounded;
}
export function parseUserProfile(value: unknown): UserProfile {
  const row = validation.object(value);
  return {
    ...parseUserResume(row),
    about: validation.optionalText(row['about'] ?? null),
    goals: validation.optionalText(row['goals'] ?? null),
    preferences: parsePreferences(row['preferences']),
    resume_settings: parseResumeSettings(row['resume_settings']),
    stories: validation.list(row['stories'] ?? [], (value): CandidateStory => {
      const story = validation.object(value);
      return {
        title: validation.identifier(story['title']),
        related_experience: validation.optionalText(story['related_experience'] ?? null),
        situation: validation.optionalText(story['situation'] ?? null),
        task: validation.optionalText(story['task'] ?? null),
        action: validation.identifier(story['action']),
        result: validation.optionalText(story['result'] ?? null),
        learning: validation.optionalText(story['learning'] ?? null),
        skills: validation.list(story['skills'] ?? [], validation.text),
        evidence: validation.list(story['evidence'] ?? [], validation.text),
      };
    }),
    answers: validation.list(row['answers'] ?? [], (value): CandidateAnswer => {
      const answer = validation.object(value);
      return {
        question: validation.identifier(answer['question']),
        answer: validation.identifier(answer['answer']),
        context: validation.optionalText(answer['context'] ?? null),
      };
    }),
  };
}
export function parseUserProfileState(value: unknown): UserProfileState {
  const row = validation.object(value);
  return {
    profile: row['profile'] === null ? null : parseUserProfile(row['profile']),
    revision: validation.number(row['revision']),
    updated_at: validation.timestamp(row['updated_at']),
  };
}
