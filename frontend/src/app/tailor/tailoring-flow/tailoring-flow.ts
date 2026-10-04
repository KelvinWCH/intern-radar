import { DOCUMENT } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  afterRenderEffect,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import {
  oneShotCallSteps,
  oneShotFlowColumns,
  oneShotFlowConnections,
  tailoringFlowColumns,
  tailoringFlowConnections,
  tailoringFlowSnowflakes,
} from '../constants/tailoring-flow.constants';
import type { DocumentDetail, OneShotStep } from '../models/document.models';
import type {
  CallStepState,
  FlowColumn,
  FlowConnection,
  FlowNode,
} from '../models/tailoring-flow.models';
import { TailoringControls } from '../tailoring-controls/tailoring-controls';

interface FlowWire {
  key: string;
  to: string;
  path: string;
  returning?: boolean;
  arrow: string;
}

type FlowPoint = readonly [x: number, y: number];

const arrowLength = 9;
const arrowWidth = 9;
const arrowNotch = 3;
const arrowGap = 2;
const bendRadius = 8;
const cardShadow = 3;

function roundedPath(points: readonly FlowPoint[]): string {
  const path: (string | number)[] = [];
  points.forEach(([x, y], index): void => {
    const previous = points[index - 1];
    const next = points[index + 1];
    const before = previous ? Math.hypot(x - previous[0], y - previous[1]) : 0;
    const after = next ? Math.hypot(next[0] - x, next[1] - y) : 0;
    if (!previous || !next || !before || !after) {
      if (path.at(-2) !== x || path.at(-1) !== y) {
        path.push(previous ? 'L' : 'M', x, y);
      }
      return;
    }
    const radius = Math.min(
      bendRadius,
      index === 1 ? before : before / 2,
      index === points.length - 2 ? after : after / 2,
    );
    path.push(
      'L',
      x + ((previous[0] - x) / before) * radius,
      y + ((previous[1] - y) / before) * radius,
      'Q',
      x,
      y,
      x + ((next[0] - x) / after) * radius,
      y + ((next[1] - y) / after) * radius,
    );
  });
  return path.join(' ');
}

function arrowHead(tip: FlowPoint, direction: FlowPoint): string {
  const [x, y] = tip;
  const [dx, dy] = direction;
  const behind = (distance: number, side: number): number[] => [
    x - dx * distance - dy * side,
    y - dy * distance + dx * side,
  ];
  return [
    'M',
    x,
    y,
    'L',
    ...behind(arrowLength, arrowWidth / 2),
    'L',
    ...behind(arrowLength - arrowNotch, 0),
    'L',
    ...behind(arrowLength, -arrowWidth / 2),
    'Z',
  ].join(' ');
}

function forwardWire(
  start: DOMRect,
  end: DOMRect,
  canvas: DOMRect,
  vertical: boolean,
): Pick<FlowWire, 'path' | 'arrow'> {
  const stacked = start.left < end.right && end.left < start.right;
  const sideBySide = start.top < end.bottom && end.top < start.bottom;
  const down = stacked || (!sideBySide && vertical);
  const point = (along: number, across: number): FlowPoint =>
    down ? [across, along] : [along, across];
  const sign = down ? Math.sign(end.top - start.top) || 1 : Math.sign(end.left - start.left) || 1;
  const forward = sign > 0;
  const origin = down ? canvas.top : canvas.left;
  let exitEdge: number;
  let entryEdge: number;
  if (down) {
    exitEdge = forward ? start.bottom : start.top;
    entryEdge = forward ? end.top : end.bottom + cardShadow;
  } else {
    exitEdge = forward ? start.right : start.left;
    entryEdge = forward ? end.left : end.right;
  }
  const exit = Math.round(exitEdge - origin);
  const entry = Math.round(entryEdge - origin);
  const center = (card: DOMRect): number =>
    Math.round(
      down ? card.left + card.width / 2 - canvas.left : card.top + card.height / 2 - canvas.top,
    );
  const target = center(end);
  const source = Math.abs(center(start) - target) <= 2 ? target : center(start);
  const bend = Math.round((exit + entry) / 2);
  const tip = entry - sign * arrowGap;
  const finish = tip - sign * (arrowLength - arrowNotch);
  return {
    path: roundedPath(
      source === target
        ? [point(exit, source), point(finish, target)]
        : [point(exit, source), point(bend, source), point(bend, target), point(finish, target)],
    ),
    arrow: arrowHead(point(tip, target), point(sign, 0)),
  };
}

@Component({
  selector: 'app-tailoring-flow',
  imports: [TailoringControls],
  templateUrl: './tailoring-flow.html',
  styleUrls: ['./tailoring-flow.scss', './tailoring-flow-states.scss'],
})
export class TailoringFlow {
  readonly document = input<DocumentDetail | null>(null);
  readonly connected = input(true);
  readonly pending = input(false);
  readonly error = input('');
  readonly changed = output<DocumentDetail>();
  protected readonly oneShot = computed((): boolean => this.document()?.mode === 'one_shot');
  protected readonly columns = computed((): readonly FlowColumn[] =>
    this.oneShot() ? oneShotFlowColumns : tailoringFlowColumns,
  );
  protected readonly callSteps = oneShotCallSteps;
  protected readonly snowflakes = tailoringFlowSnowflakes;
  protected readonly wires = signal<FlowWire[]>([]);
  private readonly nodes = computed((): FlowNode[] =>
    this.columns().flatMap((column) => [...column.nodes]),
  );
  protected readonly currentNodes = computed(() => {
    const currentStatus = [
      'awaiting_review',
      'failed',
      'cancelled',
      'paused',
      'disconnected',
      'running',
    ].find((status) => this.nodes().some((node) => this.status(node.key) === status));
    return this.nodes().filter((node) => this.status(node.key) === currentStatus);
  });
  private readonly revisionTargets = computed((): string[] => {
    const document = this.document();
    const review = document?.review;
    if (document?.status !== 'running' || document.paused_at != null) {
      return [];
    }
    if (review?.status !== 'revising') {
      return [];
    }
    const pass = review.passes.at(-1);
    if (!pass) {
      return [];
    }
    const decision = [...(review.decisions ?? [])]
      .reverse()
      .find((item) => item.round === pass.round);
    const findings = decision
      ? decision.decisions
          .filter((item) => item.action === 'revise')
          .flatMap((item) => pass.analysis.findings[item.finding_index] ?? [])
      : pass.analysis.findings.filter((finding) => finding.severity !== 'suggestion');
    return ['resume', 'cover_letter'].filter(
      (key) =>
        this.status(key) !== 'skipped' &&
        findings.some((finding) => finding.document === key || finding.document === 'both'),
    );
  });
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly page = inject(DOCUMENT);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    afterNextRender((): void => {
      const window = this.page.defaultView;
      if (!window) {
        return;
      }
      const resize =
        typeof ResizeObserver === 'undefined'
          ? null
          : new ResizeObserver((): void => {
              this.measureWires();
            });
      const canvas = this.host.nativeElement.querySelector('.flow-canvas');
      if (canvas) {
        resize?.observe(canvas);
      }
      window.addEventListener('resize', this.measureWires);
      this.measureWires();
      this.destroyRef.onDestroy((): void => {
        resize?.disconnect();
        window.removeEventListener('resize', this.measureWires);
      });
    });
    afterRenderEffect((): void => {
      this.columns();
      this.measureWires();
    });
  }

  protected callStepIcon(step: OneShotStep): string {
    return {
      done: 'pi pi-check',
      current: 'pi pi-circle-fill',
      failed: 'pi pi-times',
      waiting: 'pi pi-circle',
    }[this.callStepState(step)];
  }

  protected callStepState(step: OneShotStep): CallStepState {
    const status = this.status('one_shot');
    if (status === 'completed') {
      return 'done';
    }
    const reached =
      this.document()?.one_shot_step ??
      (['running', 'paused', 'disconnected', 'failed'].includes(status) ? 'research' : null);
    if (reached === null) {
      return 'waiting';
    }
    const order = this.callSteps.map((item) => item.key);
    const index = order.indexOf(step);
    const current = order.indexOf(reached);
    if (index < current) {
      return 'done';
    }
    if (index > current) {
      return 'waiting';
    }
    return ['failed', 'cancelled', 'not_started'].includes(status) ? 'failed' : 'current';
  }

  protected revisionActive(key: string): boolean {
    return this.connected() && this.revisionTargets().includes(key);
  }

  protected wireActive(wire: FlowWire): boolean {
    return wire.returning ? this.revisionActive(wire.to) : this.status(wire.to) === 'running';
  }

  protected wireDone(wire: FlowWire): boolean {
    return !wire.returning && ['completed', 'awaiting_review'].includes(this.status(wire.to));
  }

  protected isCurrent(key: string): boolean {
    return this.currentNodes().some((node) => node.key === key);
  }

  protected stateIcon(key: string): string {
    switch (this.status(key)) {
      case 'running':
        return 'pi pi-circle-fill';
      case 'awaiting_review':
        return 'pi pi-exclamation-circle';
      case 'failed':
      case 'not_started':
        return 'pi pi-times-circle';
      case 'disconnected':
        return 'pi pi-link';
      case 'paused':
        return 'pi pi-pause-circle';
      case 'cancelled':
        return 'pi pi-ban';
      case 'completed':
      case 'saved':
        return 'pi pi-check';
      default:
        return 'pi pi-circle';
    }
  }

  protected status(key: string): string {
    const document = this.document();
    if (!document) {
      return this.error() && !this.pending() ? 'not_started' : 'waiting';
    }
    if (key === 'source' || key === 'company' || key === 'profile') {
      return 'saved';
    }
    if (key === 'saved') {
      return document.status === 'completed' ? 'completed' : 'waiting';
    }
    const stageKey = key === 'one_shot' ? 'research' : key;
    const status =
      document.stages?.find((stage): boolean => stage.key === stageKey)?.status ?? 'waiting';
    if (status === 'running') {
      if (document.status === 'failed') {
        return 'failed';
      }
      if (document.status === 'running' && document.paused_at != null) {
        return 'paused';
      }
      if (!this.connected()) {
        return 'disconnected';
      }
    }
    return status;
  }

  protected label(key: string): string {
    const status = this.status(key);
    if (
      key === 'reviewer' &&
      status === 'running' &&
      this.document()?.review?.status === 'revising'
    ) {
      return 'Revising drafts';
    }
    if (status === 'awaiting_review') {
      return 'Needs your review';
    }
    if (key === 'one_shot' && status === 'running') {
      const reached = this.document()?.one_shot_step ?? 'research';
      return this.callSteps.find((step) => step.key === reached)?.active ?? 'In progress';
    }
    if (status === 'running') {
      return 'In progress';
    }
    const readable = status.replaceAll('_', ' ');
    return readable.charAt(0).toUpperCase() + readable.slice(1);
  }

  private readonly measureWires = (): void => {
    const host = this.host.nativeElement;
    const canvas = host.querySelector('.flow-canvas')?.getBoundingClientRect();
    if (!canvas || canvas.width === 0 || this.destroyRef.destroyed) {
      return;
    }
    const vertical = this.page.defaultView?.matchMedia('(max-width: 900px)').matches;
    const wires: FlowWire[] = [];
    const connections: readonly FlowConnection[] = this.oneShot()
      ? oneShotFlowConnections
      : tailoringFlowConnections;
    for (const [from, to] of connections) {
      const start = host.querySelector(`[data-node="${from}"]`)?.getBoundingClientRect();
      const end = host.querySelector(`[data-node="${to}"]`)?.getBoundingClientRect();
      if (!start || !end) {
        continue;
      }
      wires.push({
        key: `${from}-${to}`,
        to,
        ...forwardWire(start, end, canvas, !!vertical),
      });
    }
    const reviewer = host.querySelector('[data-node="reviewer"]')?.getBoundingClientRect();
    if (reviewer) {
      for (const key of ['resume', 'cover_letter']) {
        const writer = host.querySelector(`[data-node="${key}"]`)?.getBoundingClientRect();
        if (!writer) {
          continue;
        }
        const side = key === 'resume' ? -1 : 1;
        const lane = side * (vertical ? 14 : 18);
        let points: FlowPoint[];
        let tip: FlowPoint;
        if (vertical) {
          const sx = Math.round((side < 0 ? reviewer.left : reviewer.right) - canvas.left);
          const sy = Math.round(reviewer.top + reviewer.height / 2 - canvas.top);
          const edge = Math.round((side < 0 ? writer.left : writer.right) - canvas.left);
          const ty = Math.round(writer.top + writer.height / 2 - canvas.top);
          const outside = (side < 0 ? Math.min(sx, edge) : Math.max(sx, edge)) + lane;
          tip = [edge + side * arrowGap, ty];
          points = [
            [sx, sy],
            [outside, sy],
            [outside, ty],
            [tip[0] + side * (arrowLength - arrowNotch), ty],
          ];
        } else {
          const sx = Math.round(reviewer.left + reviewer.width / 2 - canvas.left);
          const sy = Math.round((side < 0 ? reviewer.top : reviewer.bottom) - canvas.top);
          const tx = Math.round(writer.left + writer.width / 2 - canvas.left);
          const edge = Math.round(
            (side < 0 ? writer.top : writer.bottom + cardShadow) - canvas.top,
          );
          const outside = (side < 0 ? Math.min(sy, edge) : Math.max(sy, edge)) + lane;
          tip = [tx, edge + side * arrowGap];
          points = [
            [sx, sy],
            [sx, outside],
            [tx, outside],
            [tx, tip[1] + side * (arrowLength - arrowNotch)],
          ];
        }
        wires.push({
          key: `reviewer-${key}`,
          to: key,
          path: roundedPath(points),
          returning: true,
          arrow: arrowHead(tip, vertical ? [-side, 0] : [0, -side]),
        });
      }
    }
    this.wires.update((previous) =>
      JSON.stringify(previous) === JSON.stringify(wires) ? previous : wires,
    );
  };
}
