import * as validation from '../../shared/api-validation';
import type { AiUsage } from '../../shared/models/ai.models';
import { parseAiUsage } from '../../shared/models/ai.models';

export interface ReviewFinding {
  readonly document: 'resume' | 'cover_letter' | 'both';
  readonly category: 'grounding' | 'consistency' | 'requirements' | 'writing';
  readonly severity: 'error' | 'warning' | 'suggestion';
  readonly draft_quote: string;
  readonly issue: string;
  readonly recommendation: string;
}

export interface ResumeGap {
  readonly requirement: string;
  readonly importance: 'required' | 'preferred';
  readonly status: 'not_shown' | 'no_evidence';
  readonly detail: string;
}

export interface ReviewPass {
  readonly round: number;
  readonly analysis: {
    readonly summary: string;
    readonly gaps: readonly ResumeGap[];
    readonly findings: readonly ReviewFinding[];
  };
  readonly acknowledged_finding_indices?: readonly number[];
  readonly document_hashes: Readonly<Record<string, string>>;
  readonly ai_usage: AiUsage | null;
}

export interface FindingDecision {
  readonly finding_index: number;
  readonly action: 'keep' | 'revise';
  readonly guidance: string;
}

export interface ReviewDecision {
  readonly round: number;
  readonly decisions: readonly FindingDecision[];
}

export interface ApplicationReview {
  readonly status:
    'reviewing' | 'revising' | 'awaiting_decision' | 'completed' | 'needs_attention' | 'failed';
  readonly passes: readonly ReviewPass[];
  readonly revised_documents: readonly ('resume' | 'cover_letter')[];
  readonly decisions?: readonly ReviewDecision[];
}

export interface PdfDiagnosticCheck {
  readonly key: string;
  readonly label: string;
  readonly status: 'passed' | 'warning' | 'info';
  readonly detail: string;
  readonly missing: readonly string[];
}

export interface PdfDiagnostics {
  readonly document: 'resume' | 'cover_letter';
  readonly document_sha256: string;
  readonly pdf_sha256: string;
  readonly page_count: number;
  readonly extracted_text: string;
  readonly checks: readonly PdfDiagnosticCheck[];
  readonly matched_required_skills: readonly string[];
  readonly missing_supported_skills: readonly string[];
  readonly unsupported_required_skills: readonly string[];
  readonly matched_keywords: readonly string[];
  readonly missing_supported_keywords: readonly string[];
  readonly unsupported_keywords: readonly string[];
}

function choice<T extends string>(value: unknown, choices: readonly T[]): T {
  const selected = choices.find((item): boolean => item === value);
  if (selected === undefined) {
    throw new Error('Invalid application review value.');
  }
  return selected;
}

function positiveInteger(value: unknown): number {
  const number = validation.number(value);
  if (!Number.isSafeInteger(number) || number < 1) {
    throw new Error('Invalid report count.');
  }
  return number;
}

function digest(value: unknown): string {
  const text = validation.text(value);
  if (!/^[a-f0-9]{64}$/.test(text)) {
    throw new Error('Invalid document fingerprint.');
  }
  return text;
}

function parseReviewPass(value: unknown): ReviewPass {
  const row = validation.object(value);
  const analysis = validation.object(row['analysis']);
  const round = positiveInteger(row['round']);
  const findings = validation.list(analysis['findings'], (value): ReviewFinding => {
    const finding = validation.object(value);
    return {
      document: choice(finding['document'], ['resume', 'cover_letter', 'both']),
      category: choice(finding['category'], [
        'grounding',
        'consistency',
        'requirements',
        'writing',
      ]),
      severity: choice(finding['severity'], ['error', 'warning', 'suggestion']),
      draft_quote: validation.text(finding['draft_quote']),
      issue: validation.text(finding['issue']),
      recommendation: validation.text(finding['recommendation']),
    };
  });
  const acknowledgedFindingIndices = validation.list(
    row['acknowledged_finding_indices'] ?? [],
    (value): number => {
      const index = validation.number(value);
      if (
        !Number.isSafeInteger(index) ||
        index < 0 ||
        index >= findings.length ||
        findings[index]?.severity === 'suggestion'
      ) {
        throw new Error('Invalid acknowledged finding index.');
      }
      return index;
    },
  );
  if (new Set(acknowledgedFindingIndices).size !== acknowledgedFindingIndices.length) {
    throw new Error('Duplicate acknowledged finding index.');
  }
  return {
    round,
    analysis: {
      summary: validation.text(analysis['summary']),
      gaps: validation.list(analysis['gaps'] ?? [], (value): ResumeGap => {
        const gap = validation.object(value);
        return {
          requirement: validation.text(gap['requirement']),
          importance: choice(gap['importance'], ['required', 'preferred']),
          status: choice(gap['status'], ['not_shown', 'no_evidence']),
          detail: validation.text(gap['detail']),
        };
      }),
      findings,
    },
    acknowledged_finding_indices: acknowledgedFindingIndices,
    document_hashes: Object.fromEntries(
      Object.entries(validation.object(row['document_hashes'])).map(
        ([key, value]): [string, string] => [key, digest(value)],
      ),
    ),
    ai_usage: parseAiUsage(row['ai_usage']),
  };
}

export function parseApplicationReview(value: unknown): ApplicationReview {
  const row = validation.object(value);
  return {
    status: choice(row['status'], [
      'reviewing',
      'revising',
      'awaiting_decision',
      'completed',
      'needs_attention',
      'failed',
    ]),
    passes: validation.list(row['passes'], parseReviewPass),
    decisions: validation.list(row['decisions'] ?? [], (value): ReviewDecision => {
      const decision = validation.object(value);
      return {
        round: positiveInteger(decision['round']),
        decisions: validation.list(decision['decisions'], (value): FindingDecision => {
          const item = validation.object(value);
          const index = validation.number(item['finding_index']);
          if (!Number.isSafeInteger(index) || index < 0) {
            throw new Error('Invalid finding index.');
          }
          return {
            finding_index: index,
            action: choice(item['action'], ['keep', 'revise']),
            guidance: validation.text(item['guidance'] ?? ''),
          };
        }),
      };
    }),
    revised_documents: validation.list(row['revised_documents'], (value) =>
      choice(value, ['resume', 'cover_letter']),
    ),
  };
}

export function parsePdfDiagnostics(value: unknown): PdfDiagnostics {
  const row = validation.object(value);
  return {
    document: choice(row['document'], ['resume', 'cover_letter']),
    document_sha256: digest(row['document_sha256']),
    pdf_sha256: digest(row['pdf_sha256']),
    page_count: positiveInteger(row['page_count']),
    extracted_text: validation.text(row['extracted_text']),
    checks: validation.list(row['checks'], (value): PdfDiagnosticCheck => {
      const check = validation.object(value);
      return {
        key: validation.text(check['key']),
        label: validation.text(check['label']),
        status: choice(check['status'], ['passed', 'warning', 'info']),
        detail: validation.text(check['detail']),
        missing: validation.list(check['missing'], validation.text),
      };
    }),
    matched_required_skills: validation.list(row['matched_required_skills'], validation.text),
    missing_supported_skills: validation.list(row['missing_supported_skills'], validation.text),
    unsupported_required_skills: validation.list(
      row['unsupported_required_skills'],
      validation.text,
    ),
    matched_keywords: validation.list(row['matched_keywords'] ?? [], validation.text),
    missing_supported_keywords: validation.list(
      row['missing_supported_keywords'] ?? [],
      validation.text,
    ),
    unsupported_keywords: validation.list(row['unsupported_keywords'] ?? [], validation.text),
  };
}
