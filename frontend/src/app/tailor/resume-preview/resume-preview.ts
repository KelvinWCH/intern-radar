import { Component, computed, input } from '@angular/core';
import type { GeneratedResume } from '../models/resume.models';
import type { ResumeLink } from '../models/resume-link.models';
import { profileLink, resumeLink } from '../resume-link';

@Component({
  selector: 'app-resume-preview',
  templateUrl: './resume-preview.html',
  styleUrl: './resume-preview.scss',
})
export class ResumePreview {
  readonly resume = input.required<GeneratedResume>();
  protected readonly webLink = resumeLink;
  protected phoneUrl(phone: string): string {
    return `tel:${phone.replace(/[^+0-9]/g, '')}`;
  }
  protected readonly contactLinks = computed((): ResumeLink[] => {
    const { linkedin, linkedin_label, github, links } = this.resume();
    return [
      ...(linkedin ? [profileLink(linkedin, linkedin_label)] : []),
      ...(github ? [profileLink(github)] : []),
      ...links.map(resumeLink),
    ];
  });
}
