export type OutputTone = 'neutral' | 'good' | 'warn' | 'bad' | 'accent';

export interface OutputTag {
  readonly label: string;
  readonly tone: OutputTone;
}

export interface OutputItem {
  readonly text: string;
  readonly note?: string;
  readonly tags?: readonly OutputTag[];
}

export interface OutputGroup {
  readonly title: string;
  readonly subtitle?: string;
  readonly tags?: readonly OutputTag[];
  readonly chips?: readonly string[];
  readonly items: readonly OutputItem[];
}

export type OutputSection =
  | { readonly kind: 'text'; readonly title: string; readonly text: string }
  | { readonly kind: 'items'; readonly title: string; readonly items: readonly OutputItem[] }
  | { readonly kind: 'chips'; readonly title: string; readonly chips: readonly string[] }
  | { readonly kind: 'groups'; readonly title: string; readonly groups: readonly OutputGroup[] };

export interface OutputView {
  readonly schema: string | null;
  readonly sections: readonly OutputSection[];
  readonly complete: boolean;
}

export interface OutputLabels {
  readonly experience: readonly string[];
}

export interface ReasoningRun {
  readonly text: string;
  readonly bold: boolean;
}

export interface OutputKind {
  readonly title: string;
  readonly icon: string;
}
