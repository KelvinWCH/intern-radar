import { ChangeDetectionStrategy, Component, computed, input, model } from '@angular/core';
import { FormsModule } from '@angular/forms';

export type InventoryKind = 'skills' | 'technologies' | 'coursework';

const inventoryText = {
  skills: {
    title: 'Technical skills',
    noun: 'skill',
    plural: 'skills',
    find: 'Find a skill',
    add: 'Add skills',
    example: 'e.g. Python, SQL, Bash',
    empty: 'Add your full list of skills in this category.',
    group: 'Skill inventory',
    full: 'Full skill inventory',
    defaults: 'Default resume skills',
    order: 'Default skill order',
  },
  technologies: {
    title: 'Project technologies',
    noun: 'tool',
    plural: 'tools',
    find: 'Find a technology',
    add: 'Add project technologies',
    example: 'e.g. TypeScript, Redis, Vitest',
    empty: 'Add all the tools you used, including libraries, testing tools, and infrastructure.',
    group: 'Technology inventory',
    full: 'Full technology inventory',
    defaults: 'Default resume stack',
    order: 'Default technology order',
  },
  coursework: {
    title: 'Relevant coursework',
    noun: 'course',
    plural: 'courses',
    find: 'Find a course',
    add: 'Add courses',
    example: 'e.g. Data Structures, Databases, Machine Learning',
    empty: 'Add every course you have taken here.',
    group: 'Course inventory',
    full: 'Full course inventory',
    defaults: 'Default resume courses',
    order: 'Default course order',
  },
} as const;

@Component({
  selector: 'app-inventory-selector',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule],
  templateUrl: './inventory-selector.html',
  styleUrl: './inventory-selector.scss',
})
export class InventorySelector {
  readonly kind = input<InventoryKind>('technologies');
  protected readonly text = computed(() => inventoryText[this.kind()]);
  readonly available = model.required<string[]>();
  readonly selected = model.required<string[]>();
  protected draft = '';
  protected filter = '';
  protected inventoryDraft = '';
  protected editing = false;

  protected visibleItems(): string[] {
    const query = this.filter.trim().toLocaleLowerCase();
    return this.available().filter((name) => name.toLocaleLowerCase().includes(query));
  }
  protected add(): void {
    this.available.set(this.unique([...this.available(), ...this.split(this.draft)]));
    this.draft = '';
    this.filter = '';
  }
  protected edit(): void {
    this.inventoryDraft = this.available().join('\n');
    this.editing = true;
  }
  protected apply(): void {
    const inventory = this.unique(this.split(this.inventoryDraft));
    const names = new Map(inventory.map((name) => [name.toLocaleLowerCase(), name]));
    this.available.set(inventory);
    this.selected.set(
      this.selected().flatMap((name) => {
        const updated = names.get(name.toLocaleLowerCase());
        return updated === undefined ? [] : [updated];
      }),
    );
    this.editing = false;
  }
  protected toggle(name: string): void {
    this.selected.set(
      this.selected().includes(name)
        ? this.selected().filter((item) => item !== name)
        : [...this.selected(), name],
    );
  }
  protected move(index: number, offset: number): void {
    const values = [...this.selected()];
    const current = values[index];
    const other = values[index + offset];
    if (current === undefined || other === undefined) {
      return;
    }
    values[index] = other;
    values[index + offset] = current;
    this.selected.set(values);
  }
  private split(value: string): string[] {
    return value
      .split(/[,\n]/u)
      .map((name) => name.trim())
      .filter(Boolean);
  }
  private unique(values: string[]): string[] {
    const seen = new Set<string>();
    return values.filter((value) => {
      const key = value.toLocaleLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }
}
