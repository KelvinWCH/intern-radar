import type { ReportFilters } from '../models/report-filters.models';

export const defaultReportFilters: ReportFilters = {
  area: 'gta',
  source: 'all',
  search: '',
  hideApplied: false,
  prestigeFirst: true,
  groupByCompany: false,
};

export const gtaLocationPatterns = [
  /\b(toronto|gta|north york|east york|scarborough|etobicoke|markham|richmond hill|vaughan|thornhill|woodbridge|mississauga|brampton|oakville|pickering|ajax|whitby|oshawa|newmarket|stouffville|caledon|halton hills)\b/i,
  /\b(york|burlington|milton|aurora|concord|georgetown|king city|maple)\b,?\s*(on|ontario)\b/i,
];

export const reportFiltersStorageKey = 'intern-radar.daily-report-filters';
