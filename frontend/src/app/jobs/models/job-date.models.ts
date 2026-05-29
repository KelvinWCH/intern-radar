export interface JobDateStatistic {
  readonly label: string;
  readonly help: string;
  readonly value: number | null | undefined;
  readonly dateOnly: boolean;
}
