import { DatePipe } from '@angular/common';
import type { ElementRef } from '@angular/core';
import {
  Component,
  afterRenderEffect,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { AiOutput } from '../ai-output/ai-output';
import { tailoringStepIcons, tailoringStepTones } from '../constants/tailoring-console.constants';
import type { OutputLabels } from '../models/ai-output.models';
import type { DocumentDetail, TailoringEvent } from '../models/document.models';
import { TailoringFlow } from '../tailoring-flow/tailoring-flow';
import { eventDetail, eventSource } from '../event-message';

@Component({
  selector: 'app-tailoring-console',
  imports: [AiOutput, DatePipe, TailoringFlow],
  templateUrl: './tailoring-console.html',
  styleUrl: './tailoring-console.scss',
})
export class TailoringConsole {
  readonly document = input<DocumentDetail | null>(null);
  readonly pending = input(false);
  readonly error = input('');
  readonly connected = input(true);
  readonly changed = output<DocumentDetail>();
  protected readonly notStarted = computed(
    (): boolean => !this.document() && !this.pending() && !!this.error(),
  );
  protected readonly follow = signal(true);
  protected readonly stepIcons = tailoringStepIcons;
  protected readonly stepTones = tailoringStepTones;
  protected readonly active = computed(
    (): boolean => this.pending() || this.document()?.status === 'running',
  );
  protected readonly paused = computed(
    (): boolean => this.document()?.status === 'running' && this.document()?.paused_at != null,
  );
  protected readonly events = computed(
    (): readonly TailoringEvent[] => this.document()?.events ?? [],
  );
  protected readonly selectedStages = computed(() =>
    (this.document()?.stages ?? []).filter(
      (stage) => stage.status !== 'skipped' || stage.message !== 'Not selected',
    ),
  );
  protected readonly completedStages = computed(
    (): number => this.selectedStages().filter((stage) => stage.status === 'completed').length,
  );
  protected readonly labels = computed((): OutputLabels => {
    const document = this.document();
    const resume = document?.resume ?? document?.unfitted_resume?.document;
    return {
      experience: (resume?.experience ?? []).map(
        (entry): string => `${entry.title} at ${entry.company}`,
      ),
    };
  });
  protected readonly status = computed((): { label: string; tone: string } => {
    const document = this.document();
    if (this.pending()) {
      return { label: 'Connecting', tone: 'live' };
    }
    if (this.paused()) {
      return { label: 'Paused', tone: 'warn' };
    }
    if (this.active()) {
      return this.connected()
        ? { label: 'Live', tone: 'live' }
        : { label: 'Disconnected', tone: 'warn' };
    }
    if (document?.status === 'awaiting_review') {
      return { label: 'Needs review', tone: 'warn' };
    }
    if (document?.status === 'completed') {
      return { label: 'Finished', tone: 'good' };
    }
    if (document?.status === 'cancelled') {
      return { label: 'Cancelled', tone: 'muted' };
    }
    if (this.error() || document?.status === 'failed') {
      return { label: 'Failed', tone: 'bad' };
    }
    return { label: 'Ready', tone: 'muted' };
  });
  private readonly log = viewChild<ElementRef<HTMLElement>>('log');

  constructor() {
    afterRenderEffect((): void => {
      this.document();
      this.error();
      this.pending();
      const element = this.log()?.nativeElement;
      if (element && this.follow()) {
        element.scrollTop = element.scrollHeight;
      }
    });
  }

  protected source(event: TailoringEvent): string {
    return eventSource(event.message);
  }

  protected detail(event: TailoringEvent): string {
    return eventDetail(event.message);
  }
}
