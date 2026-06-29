import type { CallStep, FlowColumn, FlowConnection } from '../models/tailoring-flow.models';

export const tailoringFlowColumns = [
  {
    label: '01 · Sources',
    tone: 'mint',
    nodes: [
      {
        key: 'source',
        label: 'Job posting',
        detail: 'Description · scraped skills',
        icon: 'pi-align-left',
      },
      {
        key: 'company',
        label: 'Company site',
        detail: 'Saved URL or looked up by name',
        icon: 'pi-globe',
      },
    ],
  },
  {
    label: '02 · Brief',
    tone: 'peach',
    nodes: [
      {
        key: 'research',
        label: 'Research brief',
        detail: 'Duties · requirements · keywords · company',
        icon: 'pi-search',
      },
      {
        key: 'profile',
        label: 'Your profile',
        detail: 'Experience · skills · stories',
        icon: 'pi-user',
      },
    ],
  },
  {
    label: '03 · Write',
    tone: 'lavender',
    nodes: [
      {
        key: 'resume',
        label: 'Resume',
        detail: 'Brief + profile',
        icon: 'pi-file',
      },
      {
        key: 'cover_letter',
        label: 'Cover letter',
        detail: 'Brief + profile',
        icon: 'pi-envelope',
      },
    ],
  },
  {
    label: '04 · Render',
    tone: 'rose',
    nodes: [
      {
        key: 'pdf_diagnostics',
        label: 'PDF checks',
        detail: 'Each draft → one-page PDF → text checks',
        icon: 'pi-file-pdf',
      },
    ],
  },
  {
    label: '05 · Review',
    tone: 'sky',
    nodes: [
      {
        key: 'reviewer',
        label: 'Independent review',
        detail: 'Drafts + posting → findings → revisions',
        icon: 'pi-verified',
      },
    ],
  },
  {
    label: '06 · Keep',
    tone: 'lime',
    nodes: [
      {
        key: 'saved',
        label: 'Document history',
        detail: 'Versions · reports · downloads',
        icon: 'pi-database',
      },
    ],
  },
] as const satisfies readonly FlowColumn[];

export const tailoringFlowConnections = [
  ['source', 'research'],
  ['company', 'research'],
  ['research', 'resume'],
  ['profile', 'resume'],
  ['research', 'cover_letter'],
  ['profile', 'cover_letter'],
  ['resume', 'pdf_diagnostics'],
  ['cover_letter', 'pdf_diagnostics'],
  ['pdf_diagnostics', 'reviewer'],
  ['reviewer', 'saved'],
] as const satisfies readonly FlowConnection[];

export const oneShotFlowColumns = [
  {
    label: '01 · Inputs',
    tone: 'mint',
    nodes: [
      {
        key: 'source',
        label: 'Job posting',
        detail: 'Description · scraped skills',
        icon: 'pi-align-left',
      },
      {
        key: 'company',
        label: 'Company site',
        detail: 'Saved URL or looked up by name',
        icon: 'pi-globe',
      },
      {
        key: 'profile',
        label: 'Your profile',
        detail: 'Experience · skills · stories',
        icon: 'pi-user',
      },
    ],
  },
  {
    label: '02 · One call',
    tone: 'lavender',
    nodes: [
      {
        key: 'one_shot',
        label: 'One AI call',
        detail: 'Researches, drafts, reviews its own drafts, then revises',
        icon: 'pi-bolt',
      },
    ],
  },
  {
    label: '03 · Check',
    tone: 'peach',
    nodes: [
      {
        key: 'resume',
        label: 'Resume',
        detail: 'Checked against your profile · fitted to one page',
        icon: 'pi-file',
      },
      {
        key: 'cover_letter',
        label: 'Cover letter',
        detail: 'Checked · fitted to one page',
        icon: 'pi-envelope',
      },
    ],
  },
  {
    label: '04 · Render',
    tone: 'rose',
    nodes: [
      {
        key: 'pdf_diagnostics',
        label: 'PDF checks',
        detail: 'One-page PDF → text checks',
        icon: 'pi-file-pdf',
      },
    ],
  },
  {
    label: '05 · Keep',
    tone: 'lime',
    nodes: [
      {
        key: 'saved',
        label: 'Document history',
        detail: 'Versions · reports · downloads',
        icon: 'pi-database',
      },
    ],
  },
] as const satisfies readonly FlowColumn[];

export const oneShotFlowConnections = [
  ['source', 'one_shot'],
  ['company', 'one_shot'],
  ['profile', 'one_shot'],
  ['one_shot', 'resume'],
  ['one_shot', 'cover_letter'],
  ['resume', 'pdf_diagnostics'],
  ['cover_letter', 'pdf_diagnostics'],
  ['pdf_diagnostics', 'saved'],
] as const satisfies readonly FlowConnection[];

export const oneShotCallSteps = [
  { key: 'research', label: 'Research', active: 'Researching' },
  { key: 'draft', label: 'Draft', active: 'Drafting' },
  { key: 'review', label: 'Self-review', active: 'Reviewing its drafts' },
  { key: 'revise', label: 'Revise', active: 'Revising' },
] as const satisfies readonly CallStep[];

export const tailoringFlowSnowflakes = Array.from({ length: 34 }, (_, index) => {
  const duration = 14 + ((index * 5) % 11);
  return {
    glyph: index % 3 === 0 ? '❄︎' : '✳︎',
    x: (index * 41 + 7) % 99,
    y: (index * 29 + 11) % 100,
    size: 11 + ((index * 7) % 12),
    duration,
    delay: -((index * 3.3) % duration),
    drift: (((index * 13) % 7) - 3) * 10,
    alpha: 0.5 + ((index * 17) % 40) / 100,
    tint: ['#8baf6d', '#719b3b', '#a9c98f', '#c5dbb0'][index % 4] ?? '#8baf6d',
  };
});
