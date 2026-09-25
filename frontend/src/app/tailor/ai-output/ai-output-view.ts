import { isRecord } from '../../shared/api-validation';
import { parsePartialJson } from '../../shared/partial-json';
import { eventSource } from '../event-message';
import {
  defaultOutputKind,
  gapTags,
  importanceTags,
  outputKinds,
  outputKindsByStep,
  severityTags,
} from '../constants/ai-output.constants';
import type {
  OutputGroup,
  OutputItem,
  OutputKind,
  OutputLabels,
  OutputSection,
  OutputTag,
  OutputView,
  ReasoningRun,
} from '../models/ai-output.models';

export function outputKind(schema: string | null | undefined, message: string): OutputKind {
  const known = schema ? outputKinds[schema] : undefined;
  return known ?? outputKindsByStep[eventSource(message) || message] ?? defaultOutputKind;
}

export function outputView(
  schema: string | null | undefined,
  text: string,
  labels: OutputLabels,
): OutputView | null {
  const parsed = parsePartialJson(text);
  const value = parsed ? record(parsed.value) : null;
  if (!parsed || !value) {
    return null;
  }
  const readAs = schema ?? inferSchema(value);
  return {
    schema: readAs,
    sections: sectionsFor(readAs ?? '', value, labels).filter(hasContent),
    complete: parsed.complete,
  };
}

export function reasoningParagraphs(text: string): ReasoningRun[][] {
  return text
    .split(/\n{2,}/u)
    .map((paragraph): string => paragraph.trim())
    .filter(Boolean)
    .map((paragraph): ReasoningRun[] =>
      paragraph
        .split('**')
        .map((run, index): ReasoningRun => ({ text: run, bold: index % 2 === 1 }))
        .filter((run): boolean => !!run.text),
    );
}

function sectionsFor(
  schema: string,
  value: Record<string, unknown>,
  labels: OutputLabels,
): OutputSection[] {
  switch (schema) {
    case 'company_role_source_plan':
      return [items('Pages to read', plain(value['urls']))];
    case 'company_role_research':
      return researchSections(value);
    case 'tailored_resume_content':
      return resumeSections(value, labels);
    case 'cover_letter_content':
      return [{ kind: 'text', title: 'Letter', text: strings(value['paragraphs']).join('\n\n') }];
    case 'application_review':
      return reviewSections(value);
    default:
      return genericSections(value);
  }
}

function inferSchema(value: Record<string, unknown>): string | null {
  if ('urls' in value) {
    return 'company_role_source_plan';
  }
  if ('role_priorities' in value || 'company_context' in value) {
    return 'company_role_research';
  }
  if ('experience' in value && 'projects' in value) {
    return 'tailored_resume_content';
  }
  if ('paragraphs' in value) {
    return 'cover_letter_content';
  }
  if ('findings' in value || 'gaps' in value) {
    return 'application_review';
  }
  return null;
}

function researchSections(value: Record<string, unknown>): OutputSection[] {
  const mission = finding(value['mission']);
  return [
    items('Mission', mission ? [mission] : []),
    items('Company context', findings(value['company_context'])),
    items('Company background (from the model, unverified)', plain(value['company_knowledge'])),
    items('Role priorities', findings(value['role_priorities'])),
    items('Requirements', findings(value['requirements'], importanceTags['required'])),
    items(
      'Preferred qualifications',
      findings(value['preferred_qualifications'], importanceTags['preferred']),
    ),
    { kind: 'chips', title: 'Keywords', chips: strings(value['keywords']) },
    items('Tailoring guidance', plain(value['tailoring_guidance'])),
    items('Typical role guidance', plain(value['general_role_guidance'])),
    items('Unknowns', plain(value['unknowns'])),
  ];
}

function resumeSections(value: Record<string, unknown>, labels: OutputLabels): OutputSection[] {
  const coverage = list(value['requirement_coverage']).flatMap((entry): OutputItem[] => {
    const row = record(entry);
    const requirement = row ? text(row['requirement']) : null;
    if (!row || !requirement) {
      return [];
    }
    const shown = list(row['evidence']).flatMap((item): string[] => {
      const evidence = record(item);
      const index = evidence ? number(evidence['source_index']) : null;
      const section = evidence ? text(evidence['section']) : null;
      return section && index !== null ? [entryName(section, index, labels)] : [];
    });
    return [
      withTags(
        {
          text: requirement,
          note: shown.length ? `Shown in ${shown.join(', ')}` : 'No supporting entry yet',
        },
        [importanceTags[text(row['importance']) ?? '']],
      ),
    ];
  });
  return [
    items('Requirement coverage', coverage),
    {
      kind: 'groups',
      title: 'Experience',
      groups: entries('experience', value['experience'], labels),
    },
    { kind: 'groups', title: 'Projects', groups: entries('project', value['projects'], labels) },
  ];
}

function entries(section: string, rows: unknown, labels: OutputLabels): OutputGroup[] {
  return list(rows).flatMap((row): OutputGroup[] => {
    const entry = record(row);
    const index = entry ? number(entry['source_index']) : null;
    if (!entry || index === null) {
      return [];
    }
    return [
      {
        title: entryName(section, index, labels),
        items: list(entry['bullets']).flatMap((item): OutputItem[] => {
          const bullet = record(item);
          const content = bullet ? text(bullet['text']) : null;
          if (!bullet || !content) {
            return [];
          }
          const original = number(bullet['source_bullet']);
          return [
            withTags({ text: content }, [
              original === null
                ? { label: 'New', tone: 'accent' }
                : { label: `Rewrites bullet ${String(original + 1)}`, tone: 'neutral' },
            ]),
          ];
        }),
      },
    ];
  });
}

function reviewSections(value: Record<string, unknown>): OutputSection[] {
  const summary = text(value['summary']);
  return [
    { kind: 'text', title: 'Summary', text: summary ?? '' },
    items(
      'Gaps',
      list(value['gaps']).flatMap((entry): OutputItem[] => {
        const gap = record(entry);
        const requirement = gap ? text(gap['requirement']) : null;
        if (!gap || !requirement) {
          return [];
        }
        const detail = text(gap['detail']);
        return [
          withTags({ text: requirement, ...(detail ? { note: detail } : {}) }, [
            importanceTags[text(gap['importance']) ?? ''],
            gapTags[text(gap['status']) ?? ''],
          ]),
        ];
      }),
    ),
    items(
      'Findings',
      list(value['findings']).flatMap((entry): OutputItem[] => {
        const found = record(entry);
        const issue = found ? text(found['issue']) : null;
        if (!found || !issue) {
          return [];
        }
        const quote = text(found['draft_quote']);
        const recommendation = text(found['recommendation']);
        const note = [quote ? `"${quote}"` : '', recommendation ?? ''].filter(Boolean).join(' - ');
        const document = text(found['document']);
        const category = text(found['category']);
        return [
          withTags({ text: issue, ...(note ? { note } : {}) }, [
            severityTags[text(found['severity']) ?? ''],
            document ? { label: words(document), tone: 'neutral' } : undefined,
            category ? { label: words(category), tone: 'neutral' } : undefined,
          ]),
        ];
      }),
    ),
  ];
}

function genericSections(value: Record<string, unknown>): OutputSection[] {
  return Object.entries(value).map(([key, field]): OutputSection => {
    const title = words(key);
    if (Array.isArray(field)) {
      return items(
        title,
        field.map((item): OutputItem => {
          const row = record(item);
          if (!row) {
            return { text: typeof item === 'string' ? item : JSON.stringify(item) };
          }
          const values = Object.values(row).filter(
            (part): part is string => typeof part === 'string',
          );
          const [first, ...rest] = values;
          return {
            text: first ?? JSON.stringify(row),
            ...(rest.length ? { note: rest.join(', ') } : {}),
          };
        }),
      );
    }
    return {
      kind: 'text',
      title,
      text: fieldText(field),
    };
  });
}

function entryName(section: string, index: number, labels: OutputLabels): string {
  return section === 'experience'
    ? (labels.experience[index] ?? `Experience ${String(index + 1)}`)
    : `Saved project ${String(index + 1)}`;
}

function findings(value: unknown, tag?: OutputTag): OutputItem[] {
  return list(value).flatMap((item): OutputItem[] => {
    const found = finding(item);
    return found ? [withTags(found, [tag])] : [];
  });
}

function finding(value: unknown): OutputItem | null {
  const row = record(value);
  const claim = row ? text(row['finding']) : null;
  if (!row || !claim) {
    return null;
  }
  const quote = text(row['quote']);
  return { text: claim, ...(quote ? { note: `"${quote}"` } : {}) };
}

function withTags(item: OutputItem, tags: readonly (OutputTag | undefined)[]): OutputItem {
  const shown = tags.filter((tag): tag is OutputTag => tag !== undefined);
  return shown.length ? { ...item, tags: shown } : item;
}

function items(title: string, entries: readonly OutputItem[]): OutputSection {
  return { kind: 'items', title, items: entries };
}

function plain(value: unknown): OutputItem[] {
  return strings(value).map((entry): OutputItem => ({ text: entry }));
}

function words(key: string): string {
  const spaced = key.replaceAll('_', ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function record(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function hasContent(section: OutputSection): boolean {
  switch (section.kind) {
    case 'text':
      return section.text !== '';
    case 'items':
      return section.items.length > 0;
    case 'chips':
      return section.chips.length > 0;
    case 'groups':
      return section.groups.length > 0;
  }
}

function fieldText(field: unknown): string {
  if (typeof field === 'string') {
    return field;
  }
  if (typeof field === 'number' || typeof field === 'boolean') {
    return String(field);
  }
  return JSON.stringify(field, null, 2);
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? (value as unknown[]) : [];
}

function strings(value: unknown): string[] {
  return list(value).filter((item): item is string => typeof item === 'string' && !!item.trim());
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function number(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}
