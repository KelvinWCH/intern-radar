export const preferenceListFields = [
  { key: 'target_roles', label: 'Target roles', placeholder: 'Software engineering\nData science' },
  { key: 'preferred_locations', label: 'Locations', placeholder: 'Toronto\nRemote' },
  { key: 'available_terms', label: 'Work terms', placeholder: 'Summer 2027' },
] as const;
export const preferenceNumberFields = [
  { key: 'graduation_year', label: 'Graduation year', min: 1900, max: 2200, step: 1 },
  { key: 'year_of_study', label: 'Academic year', min: 1, max: 20, step: 1 },
  { key: 'experience_years', label: 'Experience (years)', min: 0, max: 80, step: 0.5 },
  { key: 'gpa', label: 'GPA', min: 0, max: 100, step: 0.01 },
  { key: 'gpa_scale', label: 'GPA scale', min: 0.01, max: 100, step: 0.01 },
] as const;
export const preferenceBooleanFields = [
  { key: 'currently_enrolled', label: 'Currently enrolled?' },
  { key: 'returning_to_study', label: 'Returning to study?' },
  { key: 'requires_sponsorship', label: 'Need sponsorship?' },
] as const;
