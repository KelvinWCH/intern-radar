import * as validation from '../../shared/api-validation';
import type { AiUsage } from '../../shared/models/ai.models';
import { parseAiUsage } from '../../shared/models/ai.models';
export interface TailoringStage {
  key: string;
  label: string;
  model: string;
  status: string;
  message: string;
}
export interface ResearchFinding {
  finding: string;
  source_index: number;
  quote: string;
}
export interface ResearchSource {
  title: string;
  url: string | null;
  text: string;
}
export interface ResearchReport {
  mode: 'job_description' | 'generic';
  research_prompt: string;
  validated: boolean;
  validation_issues: string[];
  revision: number;
  approved_at: number | null;
  system_prompt: string;
  analysis: {
    mission: ResearchFinding | null;
    company_context: ResearchFinding[];
    company_knowledge: string[];
    role_priorities: ResearchFinding[];
    requirements: ResearchFinding[];
    preferred_qualifications: ResearchFinding[];
    keywords: string[];
    tailoring_guidance: string[];
    unknowns: string[];
    general_role_guidance: string[];
  };
  sources: ResearchSource[];
  warnings: string[];
  ai_usage: AiUsage | null;
  scraped_skills: ScrapedSkills | null;
}
export interface ScrapedSkills {
  required_skills: string[];
  preferred_skills: string[];
  tech_stack: string[];
}
export type ResearchAnalysis = ResearchReport['analysis'];
export interface ResearchReviewRequest {
  revision: number;
  action: 'save' | 'continue' | 'generate_generic';
  analysis?: ResearchAnalysis;
  research_prompt?: string;
}
export interface GenerationReport {
  stage: string;
  attempt: number;
  created_at: number;
  content: Record<string, unknown>;
}
export function parseStage(value: unknown): TailoringStage {
  const row = validation.object(value);
  return {
    key: validation.text(row['key']),
    label: validation.text(row['label']),
    model: validation.text(row['model']),
    status: validation.text(row['status']),
    message: validation.text(row['message']),
  };
}
export function parseFinding(value: unknown): ResearchFinding {
  const row = validation.object(value);
  return {
    finding: validation.text(row['finding']),
    source_index: validation.number(row['source_index']),
    quote: validation.text(row['quote']),
  };
}
export function parseResearch(value: unknown): ResearchReport {
  const row = validation.object(value);
  const analysis = validation.object(row['analysis']);
  const mode = validation.text(row['mode'] ?? 'job_description');
  if (mode !== 'job_description' && mode !== 'generic') {
    throw new Error('Invalid research mode');
  }
  return {
    mode,
    research_prompt: validation.text(row['research_prompt'] ?? ''),
    validated: validation.boolean(row['validated'] ?? false),
    validation_issues: validation.list(row['validation_issues'] ?? [], validation.text),
    revision: validation.number(row['revision'] ?? 1),
    approved_at: validation.timestamp(row['approved_at'] ?? null),
    system_prompt: validation.text(row['system_prompt'] ?? ''),
    analysis: {
      mission: analysis['mission'] === null ? null : parseFinding(analysis['mission']),
      company_context: validation.list(analysis['company_context'], parseFinding),
      company_knowledge: validation.list(analysis['company_knowledge'] ?? [], validation.text),
      role_priorities: validation.list(analysis['role_priorities'], parseFinding),
      requirements: validation.list(analysis['requirements'], parseFinding),
      preferred_qualifications: validation.list(
        analysis['preferred_qualifications'] ?? [],
        parseFinding,
      ),
      keywords: validation.list(analysis['keywords'] ?? [], validation.text),
      tailoring_guidance: validation.list(analysis['tailoring_guidance'], validation.text),
      unknowns: validation.list(analysis['unknowns'], validation.text),
      general_role_guidance: validation.list(
        analysis['general_role_guidance'] ?? [],
        validation.text,
      ),
    },
    warnings: validation.list(row['warnings'], validation.text),
    scraped_skills: parseScrapedSkills(row['qualifications'] ?? null),
    ai_usage: parseAiUsage(row['ai_usage']),
    sources: validation.list(row['sources'], (value): ResearchSource => {
      const source = validation.object(value);
      return {
        title: validation.text(source['title']),
        url: validation.optionalText(source['url']),
        text: validation.text(source['text']),
      };
    }),
  };
}
export function parseGenerationReport(value: unknown): GenerationReport {
  const row = validation.object(value);
  return {
    stage: validation.text(row['stage']),
    attempt: validation.number(row['attempt']),
    created_at: validation.number(row['created_at']),
    content: validation.object(row['content']),
  };
}
function parseScrapedSkills(value: unknown): ScrapedSkills | null {
  if (value === null) {
    return null;
  }
  const row = validation.object(value);
  return {
    required_skills: validation.list(row['required_skills'], validation.text),
    preferred_skills: validation.list(row['preferred_skills'], validation.text),
    tech_stack: validation.list(row['tech_stack'], validation.text),
  };
}
