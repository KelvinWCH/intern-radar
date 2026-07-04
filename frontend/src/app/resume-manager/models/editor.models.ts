export interface ProfileHeader {
  name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  linkedinLabel: string;
  github: string;
  links: string[];
}
export type ResumeSectionKey =
  | 'education'
  | 'experience'
  | 'projects'
  | 'skills'
  | 'additional_sections'
  | 'stories'
  | 'answers';
interface FieldMetadata {
  key: string;
  label: string;
  multiline: boolean;
  required: boolean;
}
export interface EditorTextField extends FieldMetadata {
  kind: 'text';
  value: string;
}
export interface EditorBulletField extends FieldMetadata {
  kind: 'bullets';
  value: string[];
  notes?: string[];
}
export interface EditorInventoryField extends FieldMetadata {
  kind: 'inventory';
  value: string[];
  available: string[];
}
export interface EditorSwitchField extends FieldMetadata {
  kind: 'switch';
  value: boolean;
}
export type EditorField =
  EditorTextField | EditorBulletField | EditorInventoryField | EditorSwitchField;
export interface EditorSection {
  key: ResumeSectionKey;
  title: string;
  entries: EditorField[][];
}
export type ProfileSectionKey = 'contact' | 'about' | 'preferences' | 'bullets' | ResumeSectionKey;
export interface EntryHeading {
  title: string;
  detail: string;
}
export interface EntryHeadingFields {
  title: string;
  details: readonly string[];
}
export type EditorFieldDefinition = readonly [
  key: string,
  label: string,
  required: boolean,
  multiline?: boolean,
];
