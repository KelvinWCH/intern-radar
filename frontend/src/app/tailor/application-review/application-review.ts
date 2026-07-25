import { Component, computed, effect, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AiUsageSummary } from '../../shared/ai-usage-summary';
import type { AiModelOptions } from '../../shared/models/ai.models';
import { ContextCompletion } from '../context-completion/context-completion';
import type {
  ApplicationReview,
  FindingDecision,
  ReviewDecision,
  ReviewFinding,
  ReviewPass,
} from '../models/application-review.models';

interface ReviewStatusLine {
  readonly tone: 'done' | 'decide' | 'warning' | 'working';
  readonly icon: string;
  readonly headline: string;
  readonly detail: string;
}

interface IndexedFinding {
  readonly index: number;
  readonly finding: ReviewFinding;
}

interface FindingGroup {
  readonly title: string;
  readonly entries: readonly IndexedFinding[];
}

interface ReviewHistoryRound {
  readonly pass: ReviewPass;
  readonly latest: boolean;
  readonly choices: readonly {
    readonly issue: string;
    readonly action: FindingDecision['action'];
    readonly guidance: string;
  }[];
}

@Component({
  selector: 'app-application-review',
  imports: [AiUsageSummary, FormsModule, RouterLink, ContextCompletion],
  templateUrl: './application-review.html',
  styleUrl: './application-review.scss',
})
export class ApplicationReviewPanel {
  readonly report = input.required<ApplicationReview>();
  readonly canDecide = input(false);
  readonly saving = input(false);
  readonly documentId = input<string | null>(null);
  readonly aiOptions = input<AiModelOptions>({});
  readonly decision = output<ReviewDecision>();
  protected readonly latest = computed(() => this.report().passes.at(-1));
  private readonly round = computed(() => this.latest()?.round);
  protected readonly choices = signal<Readonly<Record<number, 'keep' | 'revise'>>>({});
  protected readonly guidance = signal<Readonly<Record<number, string>>>({});
  protected readonly findings = computed(() => this.latest()?.analysis.findings ?? []);
  protected readonly acknowledgedFindingIndices = computed(
    () => new Set(this.latest()?.acknowledged_finding_indices ?? []),
  );
  private readonly actionableFindingIndices = computed(() =>
    this.findings().flatMap((finding, index) =>
      finding.severity !== 'suggestion' && !this.acknowledgedFindingIndices().has(index)
        ? [index]
        : [],
    ),
  );
  protected readonly actionableCount = computed(() => this.actionableFindingIndices().length);
  protected readonly remaining = computed(
    () => this.actionableFindingIndices().filter((index) => !this.choices()[index]).length,
  );
  protected readonly revisionCount = computed(
    () =>
      this.actionableFindingIndices().filter((index) => this.choices()[index] === 'revise').length,
  );
  protected readonly summaryPreviewLength = 280;
  protected readonly summaryExpanded = signal(false);
  protected readonly openQuotes = signal<ReadonlySet<number>>(new Set());
  protected readonly status = computed((): ReviewStatusLine => {
    const status = this.report().status;
    if (this.canDecide()) {
      return {
        tone: 'decide',
        icon: 'pi-question-circle',
        headline: 'How should we handle these findings?',
        detail:
          'Generation is paused. Keep each finding as is, or fix it using the evidence in your saved profile.',
      };
    }
    if (status === 'completed') {
      return {
        tone: 'done',
        icon: 'pi-check-circle',
        headline: 'Ready for your final read.',
        detail: 'No material findings remain. Read both documents before submitting.',
      };
    }
    if (status === 'needs_attention') {
      return {
        tone: 'warning',
        icon: 'pi-exclamation-circle',
        headline: 'Review finished with findings.',
        detail: 'Material findings remain unresolved. Check the documents before submitting.',
      };
    }
    if (status === 'failed') {
      return {
        tone: 'warning',
        icon: 'pi-exclamation-circle',
        headline: 'The review was interrupted.',
        detail: 'Review or revision did not finish. Saved findings may describe earlier drafts.',
      };
    }
    return {
      tone: 'working',
      icon: 'pi-clock',
      headline: 'Checking your documents.',
      detail:
        status === 'revising'
          ? 'Writers are addressing the selected findings. A fresh review follows.'
          : 'A final check has not completed yet.',
    };
  });
  protected readonly findingGroups = computed((): FindingGroup[] => {
    const entries = this.findings().map((finding, index): IndexedFinding => ({ index, finding }));
    return [
      {
        title: 'Needs attention',
        entries: entries.filter((entry) => entry.finding.severity !== 'suggestion'),
      },
      {
        title: 'Suggestions',
        entries: entries.filter((entry) => entry.finding.severity === 'suggestion'),
      },
    ].filter((group) => group.entries.length);
  });
  protected readonly historyRounds = computed((): ReviewHistoryRound[] => {
    const report = this.report();
    return report.passes.map((pass, position): ReviewHistoryRound => ({
      pass,
      latest: position === report.passes.length - 1,
      choices: (report.decisions ?? [])
        .filter((saved) => saved.round === pass.round)
        .flatMap((saved) => saved.decisions)
        .map((choice) => ({
          issue:
            pass.analysis.findings[choice.finding_index]?.issue ??
            `Finding ${String(choice.finding_index + 1)}`,
          action: choice.action,
          guidance: choice.guidance,
        })),
    }));
  });

  constructor() {
    effect((): void => {
      this.round();
      this.documentId();
      this.choices.set({});
      this.guidance.set({});
      this.summaryExpanded.set(false);
      this.openQuotes.set(new Set());
    });
  }

  protected toggleQuote(index: number): void {
    this.openQuotes.update((open): ReadonlySet<number> => {
      const next = new Set(open);
      if (!next.delete(index)) {
        next.add(index);
      }
      return next;
    });
  }

  protected choose(index: number, action: 'keep' | 'revise'): void {
    this.choices.update((choices) => ({ ...choices, [index]: action }));
  }

  protected setGuidance(index: number, value: string): void {
    this.guidance.update((notes) => ({ ...notes, [index]: value }));
  }

  protected submit(): void {
    const latest = this.latest();
    if (
      !latest ||
      !this.canDecide() ||
      this.saving() ||
      this.remaining() ||
      !this.actionableCount()
    ) {
      return;
    }
    const decisions: FindingDecision[] = [];
    this.actionableFindingIndices().forEach((index): void => {
      const action = this.choices()[index];
      if (action) {
        decisions.push({
          finding_index: index,
          action,
          guidance: action === 'revise' ? (this.guidance()[index] ?? '').trim() : '',
        });
      }
    });
    this.decision.emit({ round: latest.round, decisions });
  }

  protected skipReview(): void {
    const latest = this.latest();
    if (!latest || !this.canDecide() || this.saving() || !this.actionableCount()) {
      return;
    }
    const decisions = this.actionableFindingIndices().map((index): FindingDecision => ({
      finding_index: index,
      action: 'keep',
      guidance: '',
    }));
    this.decision.emit({ round: latest.round, decisions });
  }
}
