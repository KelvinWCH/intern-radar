export const requirementListFields = [
  ['required_skills', 'Required skills'],
  ['preferred_skills', 'Preferred skills'],
  ['tech_stack', 'Tools and technologies'],
  ['experience_requirements', 'Experience requirements'],
  ['certifications', 'Certifications'],
  ['languages', 'Languages'],
  ['other_requirements', 'Other requirements'],
] as const;

export const educationListFields = [
  ['degree_levels', 'Degree levels'],
  ['fields_of_study', 'Fields of study'],
  ['eligible_years_of_study', 'Eligible academic years'],
  ['graduation_years', 'Graduation years'],
] as const;

export const jobLinkFields = [
  ['apply_url', 'Application form URL'],
  ['company_url', 'Company URL'],
] as const;

export const jobTextFields = [
  ['source_job_id', 'Employer job ID'],
  ['category', 'Category'],
  ['sponsorship', 'Sponsorship details'],
] as const;

export const qualificationNumberFields = [
  ['minimum_experience_years', 'Minimum experience (years)', 0, 'any'],
  ['year_of_study_required', 'Required academic year', 1, '1'],
  ['minimum_gpa', 'Minimum GPA', 0, 'any'],
  ['gpa_scale', 'GPA scale', 0.01, 'any'],
] as const;

export const qualificationBooleanFields = [
  ['visa_sponsorship_available', 'Visa sponsorship available'],
  ['currently_enrolled', 'Enrollment required'],
  ['must_return_to_study', 'Must return to study'],
] as const;
