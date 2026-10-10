import { Component, model } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { CandidatePreferences } from './models/user-profile.models';

@Component({
  selector: 'app-profile-preferences',
  imports: [FormsModule],
  templateUrl: './profile-preferences.html',
  styleUrl: './profile-preferences.scss',
})
export class ProfilePreferences {
  readonly value = model.required<CandidatePreferences>();
  protected readonly listFields = preferenceListFields;
  protected readonly numberFields = preferenceNumberFields;
  protected readonly booleanFields = preferenceBooleanFields;
  protected updateList(
    key: 'target_roles' | 'preferred_locations' | 'available_terms',
    value: unknown,
  ): void {
    if (typeof value !== 'string') {
      return;
    }
    this.value.update((current): CandidatePreferences => ({
      ...current,
      [key]: value
        .split('\n')
        .map((item): string => item.trim())
        .filter(Boolean),
    }));
  }
}
import {
  preferenceBooleanFields,
  preferenceListFields,
  preferenceNumberFields,
} from './constants/preferences.constants';
