import type { ResearchReport, GenerationReport, TailoringStage } from './research.models';
import { parseResearch, parseGenerationReport, parseStage } from './research.models';
import type { ApplicationReview, PdfDiagnostics } from './application-review.models';
import { parseApplicationReview, parsePdfDiagnostics } from './application-review.models';
import type { DocumentSummary } from '../../jobs/models/user-data.models';
import { parseDocumentSummary } from '../../jobs/models/user-data.models';
import * as validation from '../../shared/api-validation';
import type { AiModelOptions, AiUsage } from '../../shared/models/ai.models';
import { parseAiOptions, parseAiUsage } from '../../shared/models/ai.models';
import type { PageNavigation } from '../../shared/models/pagination.models';
import { parseNavigation } from '../../shared/pagination';
import type { GeneratedResume } from './resume.models';
import { parseGeneratedResume } from './resume.models';
export interface CoverLetter {
  readonly ai_usage?: AiUsage | null;
  readonly name: string;
  readonly email: string | null;
  readonly phone: string | null;
  readonly location: string | null;
  readonly linkedin?: string | null;
  readonly linkedin_label?: string | null;
  readonly github?: string | null;
  readonly links: readonly string[];
  readonly company: string;
  readonly job_title: string;
  readonly greeting: string;
  readonly paragraphs: readonly string[];
  readonly closing: string;
}
export interface DocumentDownload {
  readonly blob: Blob;
  readonly filename: string;
}
export function downloadFilename(header: string | null, format: string): string | null {
  const name = /filename="([^"]+)"/iu.exec(header ?? '')?.[1];
  return name && /^[\w.-]+$/u.test(name) && name.endsWith(`.${format}`) ? name : null;
}
export interface DocumentDetail extends DocumentSummary {
  readonly mode?: TailoringMode;
  readonly one_shot_step?: OneShotStep | null;
  readonly events?: readonly TailoringEvent[];
  readonly ai_options?: AiModelOptions | null;
  readonly research_ai_options?: AiModelOptions | null;
  readonly resume_ai_options?: AiModelOptions | null;
  readonly cover_letter_ai_options?: AiModelOptions | null;
  readonly reviewer_ai_options?: AiModelOptions | null;
  readonly review?: ApplicationReview | null;
  readonly unfitted_resume?: UnfittedDraft<GeneratedResume> | null;
  readonly unfitted_cover_letter?: UnfittedDraft<CoverLetter> | null;
  readonly pdf_diagnostics?: readonly PdfDiagnostics[];
  readonly research?: ResearchReport | null;
  readonly stages?: readonly TailoringStage[];
  readonly reports?: readonly GenerationReport[];
  readonly profile_snapshot?: Record<string, unknown> | null;
  readonly profile_revision: number;
  readonly job_description: string;
  readonly paused_at?: number | null;
  readonly resume: GeneratedResume | null;
  readonly generated_resume?: GeneratedResume | null;
  readonly resume_edited_at?: number | null;
  readonly resume_revision?: number;
  readonly cover_letter: CoverLetter | null;
}

export interface UnfittedDraft<Document> {
  readonly document: Document;
  readonly overflow_lines: number;
}

export interface DocumentTechnicalDetails {
  readonly id: string;
  readonly reports: readonly GenerationReport[];
  readonly profile_snapshot: Record<string, unknown> | null;
}

export function parseDocumentTechnicalDetails(value: unknown): DocumentTechnicalDetails {
  const row = validation.object(value);
  return {
    id: validation.identifier(row['id']),
    reports: validation.list(row['reports'] ?? [], parseGenerationReport),
    profile_snapshot:
      row['profile_snapshot'] == null ? null : validation.object(row['profile_snapshot']),
  };
}
export interface TailoringEvent {
  readonly id: number;
  readonly created_at: number;
  readonly stage:
    | 'queued'
    | 'prepare'
    | 'ai'
    | 'output'
    | 'validate'
    | 'compile'
    | 'retry'
    | 'save'
    | 'done'
    | 'error'
    | 'paused'
    | 'resumed'
    | 'cancelled';
  readonly message: string;
  readonly details?: string | null;
  readonly output?: string | null;
  readonly reasoning?: string | null;
  readonly output_schema?: string | null;
}

function parseTailoringEvent(value: unknown): TailoringEvent {
  const row = validation.object(value);
  const stage = validation.text(row['stage']);
  if (
    stage !== 'queued' &&
    stage !== 'prepare' &&
    stage !== 'ai' &&
    stage !== 'output' &&
    stage !== 'validate' &&
    stage !== 'compile' &&
    stage !== 'retry' &&
    stage !== 'save' &&
    stage !== 'done' &&
    stage !== 'error' &&
    stage !== 'paused' &&
    stage !== 'resumed' &&
    stage !== 'cancelled'
  ) {
    throw new Error('Invalid tailoring stage.');
  }
  const id = validation.number(row['id']);
  if (!Number.isSafeInteger(id) || id < 1) {
    throw new Error('Invalid tailoring event ID.');
  }
  return {
    id,
    created_at: validation.number(row['created_at']),
    stage,
    message: validation.text(row['message']),
    details: validation.optionalText(row['details'] ?? null),
    output: validation.optionalText(row['output'] ?? null),
    reasoning: validation.optionalText(row['reasoning'] ?? null),
    output_schema: validation.optionalText(row['output_schema'] ?? null),
  };
}
function parseUnfitted<Document>(
  value: unknown,
  parse: (document: unknown) => Document,
): UnfittedDraft<Document> {
  const row = validation.object(value);
  const lines = validation.number(row['overflow_lines']);
  if (!Number.isInteger(lines) || lines < 0) {
    throw new Error('Invalid draft overflow.');
  }
  return { document: parse(row['document']), overflow_lines: lines };
}
export interface DocumentPage extends PageNavigation {
  readonly items: readonly DocumentSummary[];
}
export interface TailoringProcess extends DocumentSummary {
  readonly started_at: number | null;
  readonly paused_at: number | null;
  readonly stages: readonly TailoringStage[];
}

export function parseTailoringProcess(value: unknown): TailoringProcess {
  const row = validation.object(value);
  return {
    ...parseDocumentSummary(row),
    started_at: validation.timestamp(row['started_at']),
    paused_at: validation.timestamp(row['paused_at'] ?? null),
    stages: validation.list(row['stages'], parseStage),
  };
}
export type TailoringMode = 'staged' | 'one_shot';

export type OneShotStep = 'research' | 'draft' | 'review' | 'revise';

function parseOneShotStep(value: unknown): OneShotStep | null {
  if (value == null) {
    return null;
  }
  if (value === 'research' || value === 'draft' || value === 'review' || value === 'revise') {
    return value;
  }
  throw new Error('Invalid one-shot step.');
}

export interface TailorRequest {
  readonly mode?: TailoringMode;
  readonly one_shot_ai_options?: AiModelOptions;
  readonly ai_options?: AiModelOptions;
  readonly research_ai_options?: AiModelOptions;
  readonly resume_ai_options?: AiModelOptions;
  readonly cover_letter_ai_options?: AiModelOptions;
  readonly reviewer_ai_options?: AiModelOptions;
  readonly company_research_url?: string;
  readonly request_id: string;
  readonly include_resume: boolean;
  readonly include_cover_letter: boolean;
  readonly instructions?: string;
}
export function parseCoverLetter(value: unknown): CoverLetter {
  const row = validation.object(value);
  return {
    name: validation.text(row['name']),
    email: validation.optionalText(row['email']),
    phone: validation.optionalText(row['phone']),
    location: validation.optionalText(row['location']),
    linkedin: row['linkedin'] === undefined ? null : validation.optionalText(row['linkedin']),
    linkedin_label:
      row['linkedin_label'] === undefined ? null : validation.optionalText(row['linkedin_label']),
    github: row['github'] === undefined ? null : validation.optionalText(row['github']),
    links: validation.list(row['links'], validation.text),
    company: validation.text(row['company']),
    job_title: validation.text(row['job_title']),
    greeting: validation.text(row['greeting']),
    paragraphs: validation.list(row['paragraphs'], validation.text),
    closing: validation.text(row['closing']),
    ai_usage: parseAiUsage(row['ai_usage']),
  };
}
export function parseDocument(value: unknown): DocumentDetail {
  const row = validation.object(value);
  return {
    ...parseDocumentSummary(row),
    mode: row['mode'] === 'one_shot' ? 'one_shot' : 'staged',
    one_shot_step: parseOneShotStep(row['one_shot_step']),
    events: row['events'] === undefined ? [] : validation.list(row['events'], parseTailoringEvent),
    ai_options: row['ai_options'] == null ? null : parseAiOptions(row['ai_options']),
    research_ai_options:
      row['research_ai_options'] == null ? null : parseAiOptions(row['research_ai_options']),
    resume_ai_options:
      row['resume_ai_options'] == null ? null : parseAiOptions(row['resume_ai_options']),
    cover_letter_ai_options:
      row['cover_letter_ai_options'] == null
        ? null
        : parseAiOptions(row['cover_letter_ai_options']),
    research: row['research'] == null ? null : parseResearch(row['research']),
    reviewer_ai_options:
      row['reviewer_ai_options'] == null ? null : parseAiOptions(row['reviewer_ai_options']),
    review: row['review'] == null ? null : parseApplicationReview(row['review']),
    unfitted_resume:
      row['unfitted_resume'] == null
        ? null
        : parseUnfitted(row['unfitted_resume'], parseGeneratedResume),
    unfitted_cover_letter:
      row['unfitted_cover_letter'] == null
        ? null
        : parseUnfitted(row['unfitted_cover_letter'], parseCoverLetter),
    pdf_diagnostics: validation.list(row['pdf_diagnostics'] ?? [], parsePdfDiagnostics),
    stages: validation.list(row['stages'] ?? [], parseStage),
    reports: validation.list(row['reports'] ?? [], parseGenerationReport),
    profile_snapshot:
      row['profile_snapshot'] == null ? null : validation.object(row['profile_snapshot']),
    profile_revision: validation.number(row['profile_revision']),
    job_description: validation.text(row['job_description']),
    paused_at: validation.timestamp(row['paused_at'] ?? null),
    resume: row['resume'] === null ? null : parseGeneratedResume(row['resume']),
    generated_resume:
      row['generated_resume'] == null ? null : parseGeneratedResume(row['generated_resume']),
    resume_edited_at: validation.timestamp(row['resume_edited_at'] ?? null),
    resume_revision:
      row['resume_revision'] === undefined ? 0 : validation.number(row['resume_revision']),
    cover_letter: row['cover_letter'] === null ? null : parseCoverLetter(row['cover_letter']),
  };
}
export function parseDocumentPage(value: unknown): DocumentPage {
  const row = validation.object(value);
  const items = validation.list(row['items'], parseDocumentSummary);
  return {
    items,
    ...parseNavigation(row, items.length),
  };
}
