import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { EntryTools } from '../entry-tools/entry-tools';
import type { BulletLayout } from '../models/resume-editor.models';
import { layoutKey } from '../resume-draft';

@Component({
  selector: 'app-bullet-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EntryTools, FormsModule],
  templateUrl: './bullet-editor.html',
  styleUrl: './bullet-editor.scss',
})
export class BulletEditor {
  readonly items = input.required<string[]>();
  readonly label = input('Bullets');
  readonly noun = input('bullet');
  readonly name = input.required<string>();
  readonly idPrefix = input.required<string>();
  readonly section = input<'experience' | 'projects' | null>(null);
  readonly entry = input(0);
  readonly layouts = input<ReadonlyMap<string, BulletLayout>>(new Map());
  readonly addLabel = input('Add bullet');
  readonly placeholder = input('');
  readonly rows = input(2);
  readonly changed = output();

  protected set(index: number, text: string): void {
    this.items()[index] = text;
  }

  protected add(): void {
    this.items().push('');
    this.changed.emit();
  }

  protected note(text: string): string {
    const characters = text.trim().length;
    if (!characters) {
      return 'Left out while blank';
    }
    const length = `${String(characters)} characters`;
    const section = this.section();
    const layout = section ? this.layouts().get(layoutKey(section, this.entry(), text)) : undefined;
    if (!layout) {
      return length;
    }
    const amount = `about ${String(layout.characters)}`;
    switch (layout.issue) {
      case 'wrapped':
        return `${length} · runs past two lines; cut ${amount}`;
      case 'dangling':
        return `${length} · a few words spill onto line 2; cut ${amount} to fit one line`;
      case 'late':
        return `${length} · its number prints on line 2; move it earlier`;
      case 'short':
        return `${length} · 1 line, with room for ${amount} more`;
      case null:
        return `${length} · ${String(layout.lines)} line${layout.lines === 1 ? '' : 's'}`;
    }
  }

  protected issue(text: string): string | null {
    const section = this.section();
    if (!section) {
      return null;
    }
    return this.layouts().get(layoutKey(section, this.entry(), text))?.issue ?? null;
  }
}
