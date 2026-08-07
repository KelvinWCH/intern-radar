import { Clipboard } from '@angular/cdk/clipboard';
import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import type { NgForm } from '@angular/forms';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { TextareaModule } from 'primeng/textarea';
import { apiError } from '../shared/api-error';
import { LoadingIndicator } from '../shared/loading-indicator/loading-indicator';
import { Skeleton } from '../shared/skeleton/skeleton';
import { SourceResumePreview } from '../tailor/source-resume-preview/source-resume-preview';
import {
  editorData,
  editorHeader,
  editorSections,
  entryHeading,
  entryIncomplete,
  entrySwitch,
  newEntry,
} from './editor-form';
import type { EditorMode } from './models/editor-mode.models';
import type {
  EditorField,
  EditorSection,
  EditorSwitchField,
  ProfileHeader,
  ProfileSectionKey,
} from './models/editor.models';
import type { UserProfileState, UserProfile } from './models/user-profile.models';
import {
  boundedResumeSettings,
  parsePreferences,
  parseResumeSettings,
  parseUserProfile,
} from './models/user-profile.models';
import { resumeSettingFields } from './constants/resume-settings.constants';
import { entryNouns, profileSectionIcons } from './constants/editor-fields.constants';
import { ProfilePreferences } from './profile-preferences';
import { InventorySelector } from './inventory-selector/inventory-selector';
import { TranscriptCard } from './transcript-card/transcript-card';
import { ProfileSection } from './profile-section/profile-section';
import { ProfileService } from './profile.service';

@Component({
  selector: 'app-resume-manager',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    InventorySelector,
    FormsModule,
    ProfilePreferences,
    ProfileSection,
    RouterLink,
    DatePipe,
    SourceResumePreview,
    TranscriptCard,
    ButtonModule,
    InputTextModule,
    TextareaModule,
    LoadingIndicator,
    Skeleton,
  ],
  templateUrl: './resume-manager.html',
  styleUrl: './resume-manager.scss',
})
export class ResumeManager {
  private readonly service = inject(ProfileService);
  private readonly clipboard = inject(Clipboard);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly state = signal<UserProfileState | null>(null);
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly message = signal('');
  protected readonly mode = signal<EditorMode>('form');
  protected header: ProfileHeader = editorHeader(null);
  protected sections: EditorSection[] = [];
  protected json = '';
  protected preferences = parsePreferences(null);
  protected resumeSettings = parseResumeSettings(null);
  protected readonly bulletFields = resumeSettingFields;
  protected readonly icons = profileSectionIcons;
  protected readonly nouns = entryNouns;
  protected readonly entryHeading = entryHeading;
  protected readonly entryIncomplete = entryIncomplete;
  protected readonly entrySwitch = entrySwitch;
  protected readonly openSections = signal<ReadonlySet<ProfileSectionKey>>(new Set());
  private readonly addedEntries = new WeakSet<EditorField[]>();
  protected about = '';
  protected goals = '';
  constructor() {
    this.load();
  }
  protected isOpen(key: ProfileSectionKey): boolean {
    return this.openSections().has(key);
  }
  protected setOpen(key: ProfileSectionKey, open: boolean): void {
    if (this.isOpen(key) === open) {
      return;
    }
    const next = new Set(this.openSections());
    if (open) {
      next.add(key);
    } else {
      next.delete(key);
    }
    this.openSections.set(next);
  }
  protected setAllOpen(open: boolean): void {
    const keys: ProfileSectionKey[] = ['contact', 'about', 'preferences', 'bullets'];
    const sectionKeys = this.sections.map((section): ProfileSectionKey => section.key);
    this.openSections.set(new Set(open ? [...keys, ...sectionKeys] : []));
  }
  protected isAdded(entry: EditorField[]): boolean {
    return this.addedEntries.has(entry);
  }
  protected contactIncomplete(form: NgForm): boolean {
    return (
      !this.header.name.trim() ||
      ['email', 'phone'].some((name): boolean => form.controls[name]?.invalid === true)
    );
  }
  protected contactSummary(): string {
    const { name, email, phone, location } = this.header;
    const parts = [name, email, phone, location].map((part): string => part.trim()).filter(Boolean);
    return parts.length ? parts.join(' | ') : 'Add your name to save the profile';
  }
  protected aboutSummary(): string {
    const text = this.about.trim() || this.goals.trim();
    return text ? (text.split('\n')[0] ?? text) : 'Background, interests, and career goals';
  }
  protected preferencesSummary(): string {
    const { target_roles, preferred_locations, available_terms } = this.preferences;
    const parts = [target_roles, preferred_locations, available_terms]
      .filter((items): boolean => items.length > 0)
      .map((items): string => items.join(', '));
    return parts.length ? parts.join(' | ') : 'Roles, locations, work terms, and eligibility';
  }
  protected bulletsSummary(): string {
    const { min_experience_bullets, min_project_bullets } = this.resumeSettings;
    return (
      `At least ${String(min_experience_bullets)} bullets per role, ` +
      `${String(min_project_bullets)} per project`
    );
  }
  protected sectionSummary(section: EditorSection): string {
    const titles = section.entries
      .map((entry): string => {
        const title = entryHeading(section.key, entry).title;
        return title && entrySwitch(entry)?.value === false ? `${title} (off)` : title;
      })
      .filter(Boolean);
    if (titles.length) {
      return titles.join(', ');
    }
    return section.entries.length ? 'Unnamed entries' : 'Nothing added yet';
  }
  protected sectionIncomplete(section: EditorSection): boolean {
    return section.entries.some(entryIncomplete);
  }
  protected load(): void {
    this.loading.set(true);
    this.error.set('');
    this.message.set('');
    this.service
      .get()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (state): void => {
          this.populate(state);
          if (!state.profile) {
            this.setOpen('contact', true);
          }
          this.loading.set(false);
        },
        error: (error: unknown): void => {
          this.loading.set(false);
          this.error.set(apiError(error, 'Could not load your profile.'));
        },
      });
  }
  protected add(section: EditorSection): void {
    const entry = newEntry(section.key);
    this.addedEntries.add(entry);
    section.entries.push(entry);
    this.message.set('');
  }
  protected remove(section: EditorSection, index: number): void {
    section.entries.splice(index, 1);
    this.message.set('');
  }
  protected toggleEntry(field: EditorSwitchField): void {
    field.value = !field.value;
    this.message.set('');
  }
  protected addBullet(items: string[], notes?: string[]): void {
    items.push('');
    notes?.push('');
    this.message.set('');
  }
  protected removeBullet(items: string[], index: number, notes?: string[]): void {
    items.splice(index, 1);
    notes?.splice(index, 1);
    this.message.set('');
  }
  protected normalizeContact(): void {
    this.header.email = this.header.email.trim();
    const digits = this.header.phone.replace(/\D/g, '');
    const local = digits.length === 11 && digits.startsWith('1') ? digits.slice(1) : digits;
    this.header.phone =
      local.length === 10
        ? `+1 (${local.slice(0, 3)}) ${local.slice(3, 6)}-${local.slice(6)}`
        : this.header.phone.trim();
  }
  protected showJson(): void {
    if (this.mode() === 'json') {
      return;
    }
    this.json = this.draftJson();
    this.error.set('');
    this.message.set('');
    this.mode.set('json');
  }
  protected showForm(): void {
    if (this.mode() === 'form') {
      return;
    }
    const resume = this.parseJson();
    if (!resume) {
      return;
    }
    this.fill(resume);
    this.error.set('');
    this.message.set('');
    this.mode.set('form');
  }
  protected copyJson(): void {
    this.error.set('');
    if (this.clipboard.copy(this.json)) {
      this.message.set('Profile JSON copied.');
    } else {
      this.error.set('Could not copy. Select the JSON and copy it manually.');
    }
  }
  protected save(): void {
    this.normalizeContact();
    const state = this.state();
    if (!state || this.saving()) {
      return;
    }
    this.error.set('');
    this.message.set('');
    let resume: UserProfile;
    if (this.mode() === 'json') {
      const parsed = this.parseJson();
      if (!parsed) {
        return;
      }
      resume = parsed;
    } else {
      try {
        resume = parseUserProfile(this.draftData());
      } catch {
        this.error.set('Complete the required fields before saving.');
        return;
      }
    }
    this.saving.set(true);
    this.service
      .save(resume, state.revision)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (saved): void => {
          this.populate(saved);
          this.saving.set(false);
          this.message.set('Profile saved. Future tailoring will use these facts.');
        },
        error: (error: unknown): void => {
          this.saving.set(false);
          this.error.set(apiError(error, 'Could not save. Your edits are still here.'));
        },
      });
  }
  private populate(state: UserProfileState): void {
    this.state.set(state);
    this.fill(state.profile);
    if (this.mode() === 'json') {
      this.json = this.draftJson();
    }
  }
  private fill(resume: UserProfile | null): void {
    this.preferences = parsePreferences(resume?.preferences);
    this.resumeSettings = parseResumeSettings(resume?.resume_settings);
    this.about = resume?.about ?? '';
    this.goals = resume?.goals ?? '';
    this.header = editorHeader(resume);
    this.sections = editorSections(resume);
  }
  private draftData(): Record<string, unknown> {
    return {
      ...editorData(this.header, this.sections),
      about: this.about.trim() || null,
      goals: this.goals.trim() || null,
      preferences: this.preferences,
      resume_settings: boundedResumeSettings(this.resumeSettings),
    };
  }
  private draftJson(): string {
    return JSON.stringify(this.draftData(), null, 2);
  }
  private parseJson(): UserProfile | null {
    let value: unknown;
    try {
      value = JSON.parse(this.json);
    } catch (error: unknown) {
      this.error.set(
        `The JSON is not valid${error instanceof SyntaxError ? `: ${error.message}` : '.'}`,
      );
      return null;
    }
    try {
      return parseUserProfile(value);
    } catch {
      this.error.set(
        'The JSON does not match the resume format. Keep the copied field names and use text, ' +
          'lists, or null values.',
      );
      return null;
    }
  }
}
