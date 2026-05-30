import type { GeneratedResume } from './models/resume.models';
import { draftIssues, draftResume, newExperience, resumeDraft } from './resume-draft';

const resume: GeneratedResume = {
  ai_usage: {
    model_name: 'fictional',
    calls: 1,
    input_tokens: 10,
    output_tokens: 5,
  },
  requirement_coverage: [
    {
      requirement: 'Build Python APIs',
      importance: 'required',
      entries: ['Software Intern', 'Query Cache Lab'],
    },
    { requirement: 'Caching', importance: 'preferred', entries: ['Query Cache Lab'] },
    { requirement: 'Search', importance: 'preferred', entries: ['Search Project'] },
  ],
  name: 'Alex Example',
  email: 'alex@example.com',
  phone: null,
  location: 'Toronto, ON',
  linkedin: 'https://www.linkedin.com/in/alex-example',
  linkedin_label: null,
  github: null,
  links: ['https://alex.example.com'],
  education: [
    {
      institution: 'Example University',
      degree: 'BSc',
      field_of_study: 'Computer Science',
      location: null,
      start_date: '2024',
      end_date: 'Expected 2028',
      bullets: ['GPA: 3.8/4.0'],
      coursework: ['Operating Systems', 'Databases'],
    },
  ],
  experience: [
    {
      company: 'Example Co',
      title: 'Software Intern',
      location: 'Toronto',
      start_date: 'May 2026',
      end_date: 'August 2026',
      bullets: ['Built Python APIs used by 40 clinics', 'Cut p95 latency 25% with Redis caching'],
    },
  ],
  projects: [
    {
      name: 'Query Cache Lab',
      url: null,
      technologies: ['Python', 'Redis'],
      start_date: null,
      end_date: null,
      bullets: ['Served repeat search queries from a Redis cache'],
    },
    {
      name: 'Search Project',
      url: 'https://github.com/alex/search',
      technologies: ['Python'],
      start_date: '2025',
      end_date: null,
      bullets: ['Built a search service'],
    },
  ],
  skills: [{ category: 'Languages', items: ['Python', 'TypeScript'] }],
  additional_sections: [{ title: 'Awards', items: ["Dean's list"] }],
};

describe('Resume drafts', (): void => {
  it('copies the resume', (): void => {
    const draft = resumeDraft(resume);
    draft.experience[0]?.bullets.push('A new bullet');
    draft.header.links.push('https://another.example.com');
    expect(resume.experience[0]?.bullets).toHaveLength(2);
    expect(resume.links).toHaveLength(1);
  });

  it('drops blank fields', (): void => {
    const draft = resumeDraft(resume);
    draft.header.email = '   ';
    draft.header.links.push('  ');
    const [job] = draft.experience;
    if (!job) {
      throw new Error('Missing job');
    }
    job.bullets = ['  Built Python APIs used by 40 clinics  ', '', '   '];
    draft.skills.push({ category: 'Tools', items: ' , ' });
    draft.additionalSections.push({ title: 'Volunteering', items: [''] });
    const edited = draftResume(draft, resume);
    expect(edited.email).toBeNull();
    expect(edited.links).toEqual(['https://alex.example.com']);
    expect(edited.experience[0]?.bullets).toEqual(['Built Python APIs used by 40 clinics']);
    expect(edited.skills.map((group) => group.category)).toEqual(['Languages']);
    expect(edited.additional_sections.map((section) => section.title)).toEqual(['Awards']);
  });

  it('lists missing fields', (): void => {
    const draft = resumeDraft(resume);
    draft.header.name = ' ';
    draft.experience.push(newExperience());
    const [project] = draft.projects;
    if (!project) {
      throw new Error('Missing project');
    }
    project.name = '';
    draft.skills.push({ category: '', items: 'Docker' }, { category: '', items: '' });
    expect(draftIssues(draft)).toEqual([
      'Add your name.',
      'Experience 2 needs a job title.',
      'Experience 2 needs a company.',
      'Project 1 needs a name.',
      'Skill group 2 needs a category.',
    ]);
    expect(draftIssues(resumeDraft(resume))).toEqual([]);
  });
});
