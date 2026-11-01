import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { OutputLabels } from '../models/ai-output.models';
import type { TailoringEvent } from '../models/document.models';
import { outputKind, outputView, reasoningParagraphs } from './ai-output-view';

const omittedPrefix = '[Earlier output omitted from console]';

@Component({
  selector: 'app-ai-output',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe],
  templateUrl: './ai-output.html',
  styleUrl: './ai-output.scss',
})
export class AiOutput {
  readonly event = input.required<TailoringEvent>();
  readonly active = input(false);
  readonly labels = input<OutputLabels>({ experience: [] });
  protected readonly view = computed(() =>
    outputView(this.event().output_schema, this.event().output ?? '', this.labels()),
  );
  protected readonly kind = computed(() =>
    outputKind(this.view()?.schema ?? this.event().output_schema, this.event().message),
  );
  protected readonly thinking = computed(() => reasoningParagraphs(this.event().reasoning ?? ''));
  protected readonly state = computed((): 'writing' | 'done' | 'stopped' => {
    if (this.view()?.complete) {
      return 'done';
    }
    if (this.active()) {
      return 'writing';
    }
    return this.event().output?.startsWith(omittedPrefix) ? 'done' : 'stopped';
  });
}
