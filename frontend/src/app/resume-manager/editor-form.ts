import {
  arrayFieldKeys,
  entryHeadingFields,
  sectionFieldDefinitions,
  sectionTitles,
  switchableSections,
} from './constants/editor-fields.constants';
import type {
  EditorField,
  EditorSection,
  EditorSwitchField,
  EntryHeading,
  ProfileHeader,
  ResumeSectionKey,
} from './models/editor.models';
import type { UserResume } from './models/profile.models';
import { parseUserResume } from './models/profile.models';
import type { UserProfile } from './models/user-profile.models';

const inventoryKeys: Readonly<Record<string, string>> = {
  items: 'available_items',
  technologies: 'available_technologies',
  coursework: 'available_coursework',
};

function lines(value: string): string[] {
  return value
    .split('\n')
    .map((line): string => line.trim())
    .filter(Boolean);
}

function textValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item: unknown): string => (typeof item === 'string' ? item : '')).join('\n');
  }
  return '';
}

function fieldData(field: EditorField): unknown {
  if (field.kind === 'switch') {
    return field.value;
  }
  if (field.kind !== 'text') {
    return field.value.map((bullet): string => bullet.trim()).filter(Boolean);
  }
  if (arrayFieldKeys.has(field.key)) {
    return lines(field.value);
  }
  return field.required ? field.value.trim() : field.value.trim() || null;
}

export function newEntry(key: ResumeSectionKey): EditorField[] {
  const fields = sectionFieldDefinitions[key].map(
    ([name, label, required, multiline]): EditorField => {
      const metadata = { key: name, label, required, multiline: multiline ?? false };
      if (
        name === 'technologies' ||
        name === 'coursework' ||
        (key === 'skills' && name === 'items')
      ) {
        return { ...metadata, kind: 'inventory', value: [], available: [] };
      }
      if (name === 'bullets') {
        return key === 'experience' || key === 'projects'
          ? { ...metadata, kind: 'bullets', value: [], notes: [] }
          : { ...metadata, kind: 'bullets', value: [] };
      }
      return { ...metadata, kind: 'text', value: '' };
    },
  );
  if (!switchableSections.has(key)) {
    return fields;
  }
  const onResumes: EditorSwitchField = {
    key: 'enabled',
    label: 'Use on resumes',
    required: false,
    multiline: false,
    kind: 'switch',
    value: true,
  };
  return [...fields, onResumes];
}

export function entrySwitch(entry: readonly EditorField[]): EditorSwitchField | undefined {
  return entry.find((field): field is EditorSwitchField => field.kind === 'switch');
}

export function editorSections(resume: UserProfile | null): EditorSection[] {
  return (
    [
      'education',
      'experience',
      'projects',
      'skills',
      'additional_sections',
      'stories',
      'answers',
    ] as const
  ).map((key): EditorSection => ({
    key,
    title: sectionTitles[key],
    entries: (resume?.[key] ?? []).map((entry): EditorField[] => {
      const values: Record<string, unknown> = { ...entry };
      return newEntry(key).map((field): EditorField => {
        const context = values['context'];
        const contextValues: Record<string, unknown> =
          typeof context === 'object' && context !== null ? { ...context } : {};
        const value = field.key.startsWith('context.')
          ? contextValues[field.key.slice(8)]
          : values[field.key];
        if (field.kind === 'switch') {
          return { ...field, value: value !== false };
        }
        if (field.kind === 'inventory') {
          const inventory = values[inventoryKeys[field.key] ?? ''] ?? value;
          return {
            ...field,
            value: Array.isArray(value)
              ? value.filter((item: unknown): item is string => typeof item === 'string')
              : [],
            available: Array.isArray(inventory)
              ? inventory.filter((item: unknown): item is string => typeof item === 'string')
              : [],
          };
        }
        if (field.kind === 'bullets') {
          const bullets = Array.isArray(value)
            ? value.filter((item: unknown): item is string => typeof item === 'string')
            : [];
          const saved: unknown = values['bullet_context'];
          return {
            ...field,
            value: bullets,
            ...(field.notes
              ? {
                  notes: bullets.map((_bullet, index): string => {
                    const note: unknown = Array.isArray(saved) ? saved[index] : null;
                    return typeof note === 'string' ? note : '';
                  }),
                }
              : {}),
          };
        }
        return {
          ...field,
          value: textValue(value),
        };
      });
    }),
  }));
}

export function entryHeading(key: ResumeSectionKey, entry: readonly EditorField[]): EntryHeading {
  const read = (name: string): string => {
    const field = entry.find((candidate): boolean => candidate.key === name);
    if (!field || field.kind === 'switch') {
      return '';
    }
    if (field.kind === 'text') {
      return lines(field.value)[0] ?? '';
    }
    const items = field.value.map((item): string => item.trim()).filter(Boolean);
    const shown = items.slice(0, 3).join(', ');
    return items.length > 3 ? `${shown} +${String(items.length - 3)}` : shown;
  };
  const { title, details } = entryHeadingFields[key];
  return {
    title: read(title),
    detail: details
      .map((name): string =>
        name === 'dates'
          ? [read('start_date'), read('end_date')].filter(Boolean).join(' - ')
          : read(name),
      )
      .filter(Boolean)
      .join(', '),
  };
}

export function entryIncomplete(entry: readonly EditorField[]): boolean {
  return entry.some(
    (field): boolean => field.required && field.kind === 'text' && !field.value.trim(),
  );
}

export function editorHeader(resume: UserResume | null): ProfileHeader {
  return {
    name: resume?.name ?? '',
    email: resume?.email ?? '',
    phone: resume?.phone ?? '',
    location: resume?.location ?? '',
    linkedin: resume?.linkedin ?? '',
    linkedinLabel: resume?.linkedin_label ?? '',
    github: resume?.github ?? '',
    links: [...(resume?.links ?? [])],
  };
}

export function editorData(
  header: ProfileHeader,
  sections: readonly EditorSection[],
): Record<string, unknown> {
  const data: Record<string, unknown> = { name: header.name.trim() };
  for (const key of ['email', 'phone', 'location', 'linkedin', 'github'] as const) {
    data[key] = header[key].trim() || null;
  }
  data['linkedin_label'] = header.linkedinLabel.trim() || null;
  data['links'] = header.links.map((link): string => link.trim()).filter(Boolean);
  for (const section of sections) {
    data[section.key] = section.entries.map((fields): Record<string, unknown> => {
      const entry: Record<string, unknown> = Object.fromEntries(
        fields.map((field): [string, unknown] => [field.key, fieldData(field)]),
      );
      const bullets = fields.find((field) => field.kind === 'bullets');
      if (bullets?.kind === 'bullets' && bullets.notes) {
        const notes = bullets.notes;
        const kept = bullets.value.flatMap((text, index): [string, string][] =>
          text.trim() ? [[text.trim(), (notes[index] ?? '').trim()]] : [],
        );
        entry[bullets.key] = kept.map(([text]): string => text);
        entry['bullet_context'] = kept.map(([, note]): string | null => note || null);
      }
      const stack = fields.find((field) => field.kind === 'inventory');
      const inventoryKey = stack ? inventoryKeys[stack.key] : undefined;
      if (stack?.kind === 'inventory' && inventoryKey) {
        entry[inventoryKey] = stack.available;
      }
      const context: Record<string, unknown> = {};
      const result: Record<string, unknown> = {};
      for (const key of Object.keys(entry)) {
        if (key.startsWith('context.')) {
          context[key.slice(8)] = entry[key];
        } else if (key !== 'enabled' || entry[key] === false) {
          result[key] = entry[key];
        }
      }
      if (Object.keys(context).length) {
        result['context'] = context;
      }
      return result;
    });
  }
  return data;
}

export function editorResume(
  header: ProfileHeader,
  sections: readonly EditorSection[],
): UserResume {
  return parseUserResume(editorData(header, sections));
}
