import type { OneShotStep } from './document.models';

export interface FlowNode {
  readonly key: string;
  readonly label: string;
  readonly detail: string;
  readonly icon: string;
}

export interface FlowColumn {
  readonly label: string;
  readonly tone: 'mint' | 'peach' | 'lavender' | 'rose' | 'sky' | 'lime';
  readonly nodes: readonly FlowNode[];
}

export type FlowConnection = readonly [from: string, to: string];

export interface CallStep {
  readonly key: OneShotStep;
  readonly label: string;
  readonly active: string;
}

export type CallStepState = 'done' | 'current' | 'waiting' | 'failed';
