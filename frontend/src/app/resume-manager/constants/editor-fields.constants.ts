import type {
  EditorFieldDefinition,
  EntryHeadingFields,
  ProfileSectionKey,
  ResumeSectionKey,
} from '../models/editor.models';

export const contextFields: readonly EditorFieldDefinition[] = [
  ['context.company_mission', 'Company or organization mission', false, true],
  ['context.team_purpose', 'Team purpose (who did the work help?)', false, true],
  ['context.contribution', 'What I personally did', false, true],
  ['context.impact', 'Impact (results, numbers and who benefited)', false, true],
  ['context.challenges', 'Challenges and decisions', false, true],
  ['context.learnings', 'What I learned', false, true],
  ['context.tools', 'Tools I used (one per line)', false, true],
  ['context.evidence', 'Evidence links and notes (one per line)', false, true],
];

export const dateFieldDefinitions: readonly EditorFieldDefinition[] = [
  ['start_date', 'Start date', false],
  ['end_date', 'End date', false],
];

export const sectionFieldDefinitions: Record<ResumeSectionKey, readonly EditorFieldDefinition[]> = {
  education: [
    ['institution', 'Institution', true],
    ['degree', 'Degree', false],
    ['field_of_study', 'Field of study', false],
    ['location', 'Location', false],
    ...dateFieldDefinitions,
    ['coursework', 'Relevant coursework inventory and resume defaults', false, true],
    ['bullets', 'Education bullets: GPA, honors, or highlights', false, true],
  ],
  experience: [
    ['company', 'Company', true],
    ['title', 'Role', true],
    ['location', 'Location', false],
    ...dateFieldDefinitions,
    ['bullets', 'Resume bullet points', false, true],
    ['raw_description', 'Context for tailoring (paste a brag sheet)', true, true],
    ...contextFields,
  ],
  projects: [
    ['name', 'Project name', true],
    ['url', 'Project URL', false],
    ['technologies', 'Project tech stack: most relevant first', false, true],
    ...dateFieldDefinitions,
    ['bullets', 'Resume bullet points', false, true],
    ['raw_description', 'Context for tailoring (paste a brag sheet)', true, true],
    ...contextFields,
  ],
  skills: [
    ['category', 'Category', true],
    ['items', 'Skill inventory and resume defaults', false, true],
  ],
  additional_sections: [
    ['title', 'Section title', true],
    ['items', 'Entries (one per line)', true, true],
  ],
  stories: [
    ['title', 'Story title', true],
    ['related_experience', 'Related company, project, or experience', false],
    ['situation', 'Situation', false, true],
    ['task', 'Task or goal', false, true],
    ['action', 'What I did', true, true],
    ['result', 'Result and impact', false, true],
    ['learning', 'What I learned', false, true],
    ['skills', 'Skills demonstrated (one per line)', false, true],
    ['evidence', 'Evidence references (one per line)', false, true],
  ],
  answers: [
    ['question', 'Question', true, true],
    ['answer', 'My reviewed answer', true, true],
    ['context', 'When this answer applies', false, true],
  ],
};

export const sectionTitles: Record<ResumeSectionKey, string> = {
  education: 'Education',
  experience: 'Experience',
  projects: 'Projects',
  skills: 'Skills',
  additional_sections: 'Additional sections',
  stories: 'Stories',
  answers: 'Saved answers',
};

export const profileSectionIcons: Record<ProfileSectionKey, string> = {
  contact: 'pi-id-card',
  about: 'pi-user',
  preferences: 'pi-compass',
  bullets: 'pi-list',
  education: 'pi-graduation-cap',
  experience: 'pi-briefcase',
  projects: 'pi-code',
  skills: 'pi-star',
  additional_sections: 'pi-th-large',
  stories: 'pi-book',
  answers: 'pi-comments',
};

export const entryNouns: Record<ResumeSectionKey, string> = {
  education: 'school',
  experience: 'role',
  projects: 'project',
  skills: 'skill category',
  additional_sections: 'section',
  stories: 'story',
  answers: 'answer',
};

export const entryHeadingFields: Record<ResumeSectionKey, EntryHeadingFields> = {
  education: { title: 'institution', details: ['degree', 'field_of_study', 'dates'] },
  experience: { title: 'company', details: ['title', 'dates'] },
  projects: { title: 'name', details: ['technologies', 'dates'] },
  skills: { title: 'category', details: ['items'] },
  additional_sections: { title: 'title', details: ['items'] },
  stories: { title: 'title', details: ['related_experience'] },
  answers: { title: 'question', details: ['context'] },
};

export const switchableSections: ReadonlySet<ResumeSectionKey> = new Set([
  'education',
  'experience',
  'projects',
  'skills',
  'additional_sections',
]);

export const arrayFieldKeys = new Set([
  'items',
  'technologies',
  'skills',
  'evidence',
  'context.tools',
  'context.evidence',
]);
