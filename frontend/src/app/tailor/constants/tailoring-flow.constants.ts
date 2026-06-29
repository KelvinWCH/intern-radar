import type { CallStep, FlowColumn, FlowConnection } from '../models/tailoring-flow.models';

export const tailoringFlowColumns = [
  {
    label: 'Sources',
    tone: 'mint',
    nodes: [
      {
        key: 'source',
        label: 'Job posting',
        detail: 'Description and scraped skills',
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
    label: 'Brief',
    tone: 'peach',
    nodes: [
      {
        key: 'research',
        label: 'Research brief',
        detail: 'Duties, requirements, keywords, company',
        icon: 'pi-search',
      },
      {
        key: 'profile',
        label: 'Your profile',
        detail: 'Experience, skills, stories',
        icon: 'pi-user',
      },
    ],
  },
  {
    label: 'Write',
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
    label: 'Render',
    tone: 'rose',
    nodes: [
      {
        key: 'pdf_diagnostics',
        label: 'PDF checks',
        detail: 'One-page PDF, then text checks',
        icon: 'pi-file-pdf',
      },
    ],
  },
  {
    label: 'Review',
    tone: 'sky',
    nodes: [
      {
        key: 'reviewer',
        label: 'Independent review',
        detail: 'Checked against the posting, then revised',
        icon: 'pi-verified',
      },
    ],
  },
  {
    label: 'Keep',
    tone: 'lime',
    nodes: [
      {
        key: 'saved',
        label: 'Document history',
        detail: 'Versions, reports, downloads',
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
    label: 'Inputs',
    tone: 'mint',
    nodes: [
      {
        key: 'source',
        label: 'Job posting',
        detail: 'Description and scraped skills',
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
        detail: 'Experience, skills, stories',
        icon: 'pi-user',
      },
    ],
  },
  {
    label: 'One call',
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
    label: 'Check',
    tone: 'peach',
    nodes: [
      {
        key: 'resume',
        label: 'Resume',
        detail: 'Checked against your profile and fitted to one page',
        icon: 'pi-file',
      },
      {
        key: 'cover_letter',
        label: 'Cover letter',
        detail: 'Checked and fitted to one page',
        icon: 'pi-envelope',
      },
    ],
  },
  {
    label: 'Render',
    tone: 'rose',
    nodes: [
      {
        key: 'pdf_diagnostics',
        label: 'PDF checks',
        detail: 'One-page PDF, then text checks',
        icon: 'pi-file-pdf',
      },
    ],
  },
  {
    label: 'Keep',
    tone: 'lime',
    nodes: [
      {
        key: 'saved',
        label: 'Document history',
        detail: 'Versions, reports, downloads',
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
